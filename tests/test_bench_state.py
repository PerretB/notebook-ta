"""Tests for notebook_ta.bench.state.BenchAppState (run naming, dirty tracking)."""

from __future__ import annotations

from notebook_ta.bench.models import DEFAULT_SOLUTION_TAGS, ExecutionRecord, InputSnapshot
from notebook_ta.bench.state import BenchAppState
from notebook_ta.bench.storage import ProjectStore


def make_state() -> BenchAppState:
    return BenchAppState(ProjectStore(None))


class TestRunNaming:
    def test_default_run_name_is_sequential(self) -> None:
        state = make_state()
        run, _jobs = state.build_run_jobs()
        assert run.name == "Run 1"

        run2, _jobs2 = state.build_run_jobs()
        assert run2.name == "Run 2"

    def test_custom_run_name_is_used(self) -> None:
        state = make_state()
        run, _jobs = state.build_run_jobs(name="Baseline prompt")
        assert run.name == "Baseline prompt"

    def test_blank_custom_name_falls_back_to_default(self) -> None:
        state = make_state()
        run, _jobs = state.build_run_jobs(name="   ")
        assert run.name == "Run 1"

    def test_build_run_jobs_marks_dirty(self) -> None:
        state = make_state()
        assert state.dirty is False
        state.build_run_jobs()
        assert state.dirty is True


class TestRunDeletion:
    def test_delete_run_cascades_to_its_execution_records(self) -> None:
        state = make_state()
        deleted_run, _ = state.build_run_jobs(name="Delete me")
        kept_run, _ = state.build_run_jobs(name="Keep me")
        snapshot = InputSnapshot(
            exercise_statement="Example",
            tests_serialized="[]",
            student_code="answer = 1",
            exercise_hash="exercise",
            student_hash="student",
            combined_hash="combined",
        )
        for run in (deleted_run, kept_run):
            state.project.execution_records.append(
                ExecutionRecord(
                    run_id=run.id,
                    exercise_id="ex1",
                    solution_id="solution-1",
                    model_label="model-a",
                    prompt_version_id=run.prompt_version_id,
                    input_snapshot=snapshot,
                )
            )
        state.dirty = False

        assert state.delete_run(deleted_run.id) is True
        assert [run.id for run in state.project.runs] == [kept_run.id]
        assert [record.run_id for record in state.project.execution_records] == [kept_run.id]
        assert state.dirty is True

    def test_delete_missing_run_is_a_noop(self) -> None:
        state = make_state()

        assert state.delete_run("missing") is False
        assert state.dirty is False


class TestProjectLifecycle:
    def test_create_project_loads_catalog_defaults_tags_and_suggests_filename(
        self, tmp_path
    ) -> None:
        catalog = tmp_path / "exercises.toml"
        catalog.write_text(
            '[exercises.add]\nstatement = "Add two numbers."\n', encoding="utf-8"
        )
        state = BenchAppState(ProjectStore(None), project_open=False)

        state.create_project("My: benchmark.json", catalog)

        assert state.project_open is True
        assert state.store.path is None
        assert state.suggested_project_filename == "My- benchmark.json"
        assert state.project.settings.known_tags == DEFAULT_SOLUTION_TAGS
        assert list(state.exercise_registry) == ["add"]
        assert state.dirty is True

    def test_close_project_returns_to_welcome_state(self) -> None:
        state = make_state()
        state.mark_dirty()

        state.close_project()

        assert state.project_open is False
        assert state.exercise_registry == {}
        assert state.store.path is None
        assert state.dirty is False
