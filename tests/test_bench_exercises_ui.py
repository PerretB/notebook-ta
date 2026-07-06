"""Interaction tests for the benchmarking exercise solution controls."""

from __future__ import annotations

from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from notebook_ta.bench.state import BenchAppState
from notebook_ta.bench.storage import ProjectStore
from notebook_ta.bench.ui.exercises_tab import _build_solutions, build
from notebook_ta.config.models import ExerciseConfig

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
    user.find("Solution name").type("Reference solution")
    assert state.exercise_registry["ex1"].name == "Renamed exercise"
    assert solution.label == "Reference solution"

    user.find("Add exercise").click()
    user.find("Exercise ID").type("ex2")
    user.find("New exercise name").type("Second exercise")
    user.find("Statement").type("A new problem")
    user.find("Create exercise").click()

    assert state.exercise_registry["ex2"].name == "Second exercise"
    reloaded = catalog_path.read_text(encoding="utf-8")
    assert "Renamed exercise" in reloaded
    assert "Second exercise" in reloaded
    await user.should_see("Second exercise")
