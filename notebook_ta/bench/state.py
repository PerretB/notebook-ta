"""In-process application state for the benchmarking GUI.

`BenchAppState` owns the active `BenchProject`, the exercise catalog reloaded from
the source TOML file, and the `BenchExecutor`. UI modules mutate the project
exclusively through this class so that dirty-tracking (`mark_dirty()`) is never
forgotten.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from notebook_ta.bench.catalog import add_exercise as add_catalog_exercise
from notebook_ta.bench.catalog import set_exercise_name
from notebook_ta.bench.executor import BenchExecutor, BenchJob, ProgressCallback, build_jobs
from notebook_ta.bench.models import (
    BenchmarkRun,
    BenchProject,
    ExecutionRecord,
    ModelUnderTest,
    PromptVersion,
    StudentSolution,
)
from notebook_ta.bench.storage import ProjectStore
from notebook_ta.config.loader import load_exercises
from notebook_ta.config.models import ConfigurationError, ExerciseConfig
from notebook_ta.logging import get_logger

_log = get_logger("bench.state")


def _project_filename(name: str) -> str:
    """Convert a user-facing project name into a safe default JSON filename."""
    safe_name = "".join("-" if character in '<>:"/\\|?*' else character for character in name)
    safe_name = safe_name.strip(" .")
    if safe_name.lower().endswith(".json"):
        safe_name = safe_name[:-5].rstrip(" .")
    return f"{safe_name or 'benchmark-project'}.json"


class BenchAppState:
    """Owns the active `BenchProject`, exercise catalog, and benchmark executor."""

    def __init__(
        self,
        store: ProjectStore,
        *,
        project_open: bool = True,
        recent_project_path: str | Path | None = None,
    ) -> None:
        self.store = store
        self.project: BenchProject = store.load()
        self.project_open = project_open
        self.recent_project_path = Path(recent_project_path) if recent_project_path else None
        self.suggested_project_filename = (
            store.path.name if store.path is not None else "benchmark-project.json"
        )
        self.exercise_registry: dict[str, ExerciseConfig] = {}
        self.dirty: bool = False
        self.active_run: BenchmarkRun | None = None
        self.executor = BenchExecutor(lambda: self.project.settings.python_path_dirs)
        if self.project.settings.exercises_toml_path:
            self.reload_exercise_catalog()

    # -- persistence -------------------------------------------------------

    def mark_dirty(self) -> None:
        """Flag the project as having unsaved changes."""
        self.dirty = True

    def save_now(self) -> None:
        """Save the project immediately and clear the dirty flag."""
        self.store.save(self.project)
        self.dirty = False

    def save_as(self, path: str | Path) -> None:
        """Save the project to a new path and remember it as the active path."""
        self.store.save_as(self.project, Path(path))
        self.suggested_project_filename = Path(path).name
        self.recent_project_path = Path(path)
        self.dirty = False

    def load_from(self, path: str | Path) -> None:
        """Replace the current project with one loaded from `path`."""
        new_path = Path(path)
        new_store = ProjectStore(new_path)
        new_project = new_store.load()
        new_registry: dict[str, ExerciseConfig] = {}
        if new_project.settings.exercises_toml_path:
            exercises = load_exercises(new_project.settings.exercises_toml_path)
            new_registry = {exercise.id: exercise for exercise in exercises}

        self.store = new_store
        self.project = new_project
        self.exercise_registry = new_registry
        self.dirty = False
        self.project_open = True
        self.recent_project_path = new_path
        self.suggested_project_filename = new_path.name
        self.executor = BenchExecutor(lambda: self.project.settings.python_path_dirs)

    def create_project(self, name: str, exercises_toml_path: str | Path) -> None:
        """Create a new unsaved project initialized from an exercise TOML catalog."""
        normalized_name = name.strip()
        if not normalized_name:
            raise ConfigurationError("Project name cannot be empty.")
        catalog_path = Path(exercises_toml_path)
        exercises = load_exercises(catalog_path)

        self.store = ProjectStore(None)
        self.project = self.store.load()
        self.project.settings.exercises_toml_path = str(catalog_path)
        self.exercise_registry = {exercise.id: exercise for exercise in exercises}
        self.executor = BenchExecutor(lambda: self.project.settings.python_path_dirs)
        self.active_run = None
        self.project_open = True
        self.suggested_project_filename = _project_filename(normalized_name)
        self.mark_dirty()

    def close_project(self) -> None:
        """Discard the in-memory workspace and return to the no-project-open state."""
        if self.active_run is not None:
            raise ConfigurationError("Cannot close a project while a benchmark run is active.")
        self.store = ProjectStore(None)
        self.project = self.store.load()
        self.exercise_registry = {}
        self.executor = BenchExecutor(lambda: self.project.settings.python_path_dirs)
        self.active_run = None
        self.project_open = False
        self.suggested_project_filename = "benchmark-project.json"
        self.dirty = False

    # -- exercise catalog ----------------------------------------------------

    def reload_exercise_catalog(self) -> None:
        """(Re)load the exercise TOML catalog referenced by project settings."""
        path = self.project.settings.exercises_toml_path
        if not path:
            self.exercise_registry = {}
            return
        exercises = load_exercises(path)
        self.exercise_registry = {ex.id: ex for ex in exercises}
        _log.debug("Loaded %d exercises from %s", len(self.exercise_registry), path)

    def add_exercise(self, exercise_id: str, name: str = "", statement: str = "") -> ExerciseConfig:
        """Create an exercise and persist it to the configured local TOML catalog."""
        normalized_id = exercise_id.strip()
        if not normalized_id:
            raise ConfigurationError("Exercise ID cannot be empty.")
        if normalized_id in self.exercise_registry:
            raise ConfigurationError(f"Exercise {normalized_id!r} already exists.")
        exercise = ExerciseConfig(
            id=normalized_id,
            name=name.strip() or None,
            statement=statement.strip() or None,
        )
        add_catalog_exercise(self._editable_catalog_path(), exercise)
        self.exercise_registry[exercise.id] = exercise
        return exercise

    def update_exercise_name(self, exercise_id: str, name: str) -> None:
        """Update an exercise display name in memory and in the local TOML catalog."""
        exercise = self.exercise_registry[exercise_id]
        normalized_name = name.strip()
        set_exercise_name(self._editable_catalog_path(), exercise_id, normalized_name)
        exercise.name = normalized_name or None

    def _editable_catalog_path(self) -> str:
        """Return the configured catalog path or raise a descriptive authoring error."""
        path = self.project.settings.exercises_toml_path
        if not path:
            raise ConfigurationError(
                "Configure a local exercises.toml path in Settings before editing exercises."
            )
        if path.startswith(("http://", "https://")):
            raise ConfigurationError("Remote exercise catalogs are read-only.")
        return path

    # -- solutions -----------------------------------------------------------

    def add_solution(
        self,
        exercise_id: str,
        code: str = "",
        label: str = "",
        tags: list[str] | None = None,
        generated_by_internal_model: bool = False,
    ) -> StudentSolution:
        """Create and register a new student solution for `exercise_id`."""
        solution = StudentSolution(
            exercise_id=exercise_id,
            code=code,
            label=label,
            tags=tags or [],
            generated_by_internal_model=generated_by_internal_model,
        )
        self.project.solutions.append(solution)
        self.mark_dirty()
        return solution

    def remove_solution(self, solution_id: str) -> None:
        """Remove a student solution by ID."""
        self.project.solutions = [s for s in self.project.solutions if s.id != solution_id]
        self.mark_dirty()

    def update_solution_label(self, solution_id: str, label: str) -> None:
        """Update the editable display name of a student solution."""
        solution = next(s for s in self.project.solutions if s.id == solution_id)
        solution.label = label
        self.mark_dirty()

    # -- models under test -----------------------------------------------------

    def add_model(self, model: ModelUnderTest) -> None:
        """Register a model as a candidate for benchmarking."""
        self.project.models_under_test.append(model)
        self.mark_dirty()

    def remove_model(self, label: str) -> None:
        """Remove a model under test by its label."""
        self.project.models_under_test = [
            m for m in self.project.models_under_test if m.label != label
        ]
        self.project.draft_selected_model_labels = [
            lbl for lbl in self.project.draft_selected_model_labels if lbl != label
        ]
        self.mark_dirty()

    # -- benchmark execution -----------------------------------------------------

    def build_run_jobs(self, name: str = "") -> tuple[BenchmarkRun, list[BenchJob]]:
        """Freeze the active draft prompt into a new PromptVersion and build the job matrix."""
        prompt_version = PromptVersion(
            id=self.project.next_prompt_version_id(),
            on_success=self.project.draft_prompt_on_success,
            on_failure=self.project.draft_prompt_on_failure,
        )
        self.project.prompt_versions.append(prompt_version)

        selected = [
            m
            for m in self.project.models_under_test
            if m.label in self.project.draft_selected_model_labels
        ]
        solutions_by_exercise: dict[str, list[StudentSolution]] = {}
        for solution in self.project.solutions:
            solutions_by_exercise.setdefault(solution.exercise_id, []).append(solution)

        jobs = build_jobs(
            list(self.exercise_registry.values()), solutions_by_exercise, selected, prompt_version
        )

        run = BenchmarkRun(
            name=name.strip() or f"Run {len(self.project.runs) + 1}",
            prompt_version_id=prompt_version.id,
            model_labels=[m.label for m in selected],
            job_count=len(jobs),
        )
        self.project.runs.append(run)
        self.mark_dirty()
        return run, jobs

    async def run_benchmark(
        self, jobs: list[BenchJob], run: BenchmarkRun, on_progress: ProgressCallback
    ) -> None:
        """Run `jobs` sequentially, persisting each completed/failed record as it arrives."""

        def _combined(
            job: BenchJob, status: str, message: str | None, record: ExecutionRecord | None
        ) -> None:
            if record is not None:
                self.project.execution_records.append(record)
                self.mark_dirty()
            on_progress(job, status, message, record)

        self.active_run = run
        await self.executor.run(jobs, run, _combined)
        self.active_run = None

    def delete_run(self, run_id: str) -> bool:
        """Delete a benchmark run and all execution records produced by it.

        Returns ``True`` when a matching run was deleted and ``False`` when the
        run no longer exists.
        """
        original_count = len(self.project.runs)
        self.project.runs = [run for run in self.project.runs if run.id != run_id]
        if len(self.project.runs) == original_count:
            return False
        self.project.execution_records = [
            record for record in self.project.execution_records if record.run_id != run_id
        ]
        self.mark_dirty()
        return True

    def rerun_job(
        self, exercise_id: str, solution_id: str, model_label: str, prompt_version_id: str
    ) -> Callable[[], Coroutine[Any, Any, ExecutionRecord]]:
        """Return an async callable that re-executes exactly one job (Compare tab "Re-run")."""
        config = self.exercise_registry[exercise_id]
        solution = next(s for s in self.project.solutions if s.id == solution_id)
        model = next(m for m in self.project.models_under_test if m.label == model_label)
        prompt_version = next(p for p in self.project.prompt_versions if p.id == prompt_version_id)

        run = BenchmarkRun(
            prompt_version_id=prompt_version_id, model_labels=[model_label], job_count=1
        )
        self.project.runs.append(run)
        job = BenchJob(config, solution, model, prompt_version)

        async def _do_rerun() -> ExecutionRecord:
            record = await self.executor.run_single(job, run)
            self.project.execution_records.append(record)
            self.mark_dirty()
            return record

        return _do_rerun
