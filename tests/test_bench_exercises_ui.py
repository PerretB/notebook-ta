"""Interaction tests for the benchmarking exercise solution controls."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from nicegui import ui
from nicegui.testing import User

from notebook_ta.bench.state import BenchAppState
from notebook_ta.bench.storage import ProjectStore
from notebook_ta.bench.ui.exercises_tab import _build_solutions, build
from notebook_ta.config.models import ExerciseConfig, TestDefinition
from notebook_ta.testing.runner import TestResult as RunnerResult

pytest_plugins = ["nicegui.testing.user_plugin"]


@pytest.mark.asyncio
@pytest.mark.nicegui_main_file("notebook_ta/bench/app.py")
async def test_add_and_remove_solution_actions_ignore_queued_duplicate_clicks(
    user: User,
) -> None:
    """A stale control must not apply its mutation twice after the list refreshes."""
    state = BenchAppState(ProjectStore(None))
    exercise = ExerciseConfig(id="ex1", statement="Example")
    state.exercise_registry[exercise.id] = exercise
    state.add_solution(exercise.id)

    @ui.page("/")
    def page() -> None:
        """Render the solution controls under test."""
        _build_solutions(state, exercise)

    await user.open("/")
    await user.should_see("Student solutions (1)")

    add = user.find("Add blank solution")
    add.click()
    add.click()

    assert len(state.project.solutions_for(exercise.id)) == 2
    await user.should_see("Student solutions (2)")

    remove = user.find("Remove")
    remove.click()
    remove.click()

    assert len(state.project.solutions_for(exercise.id)) == 1
    await user.should_see("Student solutions (1)")


@pytest.mark.asyncio
@pytest.mark.nicegui_main_file("notebook_ta/bench/app.py")
async def test_run_tests_renders_ansi_messages_as_html(user: User) -> None:
    """Bench test results should render ANSI colors instead of showing control codes."""
    state = BenchAppState(ProjectStore(None))
    exercise = ExerciseConfig(id="ex1", statement="Example")
    state.exercise_registry[exercise.id] = exercise
    state.add_solution(exercise.id, code="answer = 1")

    @ui.page("/")
    def page() -> None:
        """Render the solution controls under test."""
        _build_solutions(state, exercise)

    result = RunnerResult(
        name="custom",
        passed=True,
        message="\033[92m✔ 1/1 tests passed.\033[0m",
    )
    worker_result = SimpleNamespace(test_results=[result], error=None)
    with patch(
        "notebook_ta.bench.ui.exercises_tab.run_solution_tests_with_timeout",
        return_value=worker_result,
    ):
        await user.open("/")
        user.find("Run tests").click()
        await user.should_see("1/1 tests passed.")

    rendered_html = [element.content for element in user.find(ui.html).elements]
    assert any("color: #00c000" in content for content in rendered_html)
    assert all("\033[" not in content for content in rendered_html)


@pytest.mark.asyncio
@pytest.mark.nicegui_main_file("notebook_ta/bench/app.py")
async def test_run_tests_drops_duplicate_clicks_when_setup_code_exists(user: User) -> None:
    """A queued duplicate Run tests click must not run or render test results twice."""
    state = BenchAppState(ProjectStore(None))
    exercise = ExerciseConfig(id="ex1", statement="Example")
    state.exercise_registry[exercise.id] = exercise
    state.project.setup_code_by_exercise[exercise.id] = "expected = 1"
    state.add_solution(exercise.id, code="answer = 1")

    @ui.page("/")
    def page() -> None:
        """Render the solution controls under test."""
        _build_solutions(state, exercise)

    result = RunnerResult(name="custom", passed=True, message="passed once")
    worker_result = SimpleNamespace(test_results=[result], error=None)
    with patch(
        "notebook_ta.bench.ui.exercises_tab.run_solution_tests_with_timeout",
        return_value=worker_result,
    ) as run:
        await user.open("/")
        button = user.find("Run tests")
        button.click()
        button.click()
        await user.should_see("passed once")
        await asyncio.sleep(0.3)

    assert run.call_count == 1
    rendered_html = [element.content for element in user.find(ui.html).elements]
    assert sum("passed once" in content for content in rendered_html) == 1


@pytest.mark.asyncio
@pytest.mark.nicegui_main_file("notebook_ta/bench/app.py")
async def test_run_tests_executes_editable_code_outside_server_process(
    user: User, tmp_path: Path
) -> None:
    """The preview path must execute solution code in the spawned worker PID."""
    worker_pid_path = tmp_path / "worker-pid.txt"
    state = BenchAppState(ProjectStore(None))
    exercise = ExerciseConfig(
        id="ex1",
        statement="Example",
        tests=[TestDefinition(name="checks answer", code="def check(answer): return answer == 1")],
    )
    state.exercise_registry[exercise.id] = exercise
    state.add_solution(
        exercise.id,
        code=(
            "import os\n"
            "from pathlib import Path\n"
            f"Path({str(worker_pid_path)!r}).write_text(str(os.getpid()))\n"
            "answer = 1\n"
        ),
    )

    @ui.page("/")
    def page() -> None:
        """Render the solution controls under test."""
        _build_solutions(state, exercise)

    await user.open("/")
    user.find("Run tests").click()
    await user.should_see("checks answer", retries=100)

    assert int(worker_pid_path.read_text(encoding="utf-8")) != os.getpid()


@pytest.mark.asyncio
@pytest.mark.nicegui_main_file("notebook_ta/bench/app.py")
async def test_run_tests_reports_when_exercise_has_no_tests(user: User) -> None:
    """Exercises without tests should produce visible feedback instead of appearing inert."""
    state = BenchAppState(ProjectStore(None))
    exercise = ExerciseConfig(id="ex1", statement="Example", tests=[])
    state.exercise_registry[exercise.id] = exercise
    state.add_solution(exercise.id, code="answer = 1")

    @ui.page("/")
    def page() -> None:
        """Render the solution controls under test."""
        _build_solutions(state, exercise)

    await user.open("/")
    user.find("Run tests").click()

    await user.should_see("No unit tests are configured for this exercise.", retries=100)


@pytest.mark.asyncio
@pytest.mark.nicegui_main_file("notebook_ta/bench/app.py")
async def test_exercises_are_expanded_and_names_and_new_exercises_are_editable(
    user: User,
    tmp_path: Path,
) -> None:
    """The exercise authoring view must expose expanded, persisted editing controls."""
    catalog_path = tmp_path / "exercises.toml"
    catalog_path.write_text(
        '[exercises.ex1]\nstatement = "Example"\n',
        encoding="utf-8",
    )
    state = BenchAppState(ProjectStore(None))
    state.project.settings.exercises_toml_path = str(catalog_path)
    state.reload_exercise_catalog()
    solution = state.add_solution("ex1")

    @ui.page("/")
    def page() -> None:
        """Render the complete exercise authoring view under test."""
        build(state)

    await user.open("/")

    expansions = user.find(ui.expansion).elements
    assert len(expansions) == 1
    assert next(iter(expansions)).value is True

    user.find("Exercise name").type("Renamed exercise")
    user.find("Add setup code").click()
    user.find(ui.codemirror).type("expected = 5")
    user.find("Save setup code").click()
    user.find("Solution name").type("Reference solution")
    assert state.exercise_registry["ex1"].name == "Renamed exercise"
    assert state.project.setup_code_for("ex1") == "expected = 5"
    assert solution.label == "Reference solution"

    user.find("Add exercise").click()
    user.find("Exercise ID").type("ex2")
    user.find("New exercise name").type("Second exercise")
    user.find("Statement").type("A new problem")
    user.find("Create exercise").click()

    assert state.exercise_registry["ex2"].name == "Second exercise"
    reloaded = catalog_path.read_text(encoding="utf-8")
    assert "Renamed exercise" in reloaded
    assert "expected = 5" not in reloaded
    assert "Second exercise" in reloaded
    await user.should_see("Second exercise")
