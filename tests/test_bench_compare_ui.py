"""Tests for the benchmark comparison matrix."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from nicegui import ui
from nicegui.testing import User

from notebook_ta.bench.hashing import build_input_snapshot
from notebook_ta.bench.models import (
    BenchmarkRun,
    ExecutionMetrics,
    ExecutionRecord,
    PromptVersion,
)
from notebook_ta.bench.state import BenchAppState
from notebook_ta.bench.storage import ProjectStore
from notebook_ta.bench.ui.compare_tab import (
    _default_combinations,
    _open_delete_run_dialog,
    build,
)
from notebook_ta.config.models import ExerciseConfig

pytest_plugins = ["nicegui.testing.user_plugin"]


def _make_state_with_history() -> BenchAppState:
    """Create state containing two solutions and two historical comparison columns."""
    state = BenchAppState(ProjectStore(None))
    exercise = ExerciseConfig(id="ex1", statement="Complete exercise directions")
    state.exercise_registry[exercise.id] = exercise
    first = state.add_solution(exercise.id, label="Solution A", code="answer = 1")
    first.tags = ["correct"]
    second = state.add_solution(exercise.id, label="Solution B", code="answer = 2")
    project = state.project
    project.prompt_versions.extend(
        [
            PromptVersion(
                id="V1",
                on_success="old",
                on_failure="old",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            PromptVersion(
                id="V2",
                on_success="new",
                on_failure="new",
                created_at=datetime(2026, 2, 1, tzinfo=UTC),
            ),
        ]
    )
    project.runs.extend(
        [
            BenchmarkRun(
                id="run-1",
                prompt_version_id="V1",
                model_labels=["model-a"],
                status="completed",
            ),
            BenchmarkRun(
                id="run-2",
                prompt_version_id="V2",
                model_labels=["model-a", "model-b"],
                status="completed",
            ),
        ]
    )
    for index, solution in enumerate((first, second), start=1):
        for model in ("model-a", "model-b"):
            project.execution_records.append(
                ExecutionRecord(
                    run_id="run-2",
                    exercise_id=exercise.id,
                    solution_id=solution.id,
                    model_label=model,
                    prompt_version_id="V2",
                    input_snapshot=build_input_snapshot(exercise, solution),
                    llm_output=f"V2 feedback for {solution.label} from {model}",
                    metrics=ExecutionMetrics(
                        time_to_first_token_s=float(index),
                        total_generation_time_s=float(index + 1),
                        throughput_tokens_per_s=float(index * 10),
                    ),
                )
            )
    project.execution_records.insert(
        0,
        ExecutionRecord(
            run_id="run-1",
            exercise_id=exercise.id,
            solution_id=first.id,
            model_label="model-a",
            prompt_version_id="V1",
            input_snapshot=build_input_snapshot(exercise, first),
            llm_output="V1 old feedback",
        ),
    )
    return state


def test_latest_run_combinations_are_selected_by_default() -> None:
    """Default columns must come from the newest run with available records."""
    project = _make_state_with_history().project
    combinations = [
        (record.model_label, record.prompt_version_id)
        for record in project.execution_records
    ]

    assert _default_combinations(project, combinations) == [
        ("model-a", "V2"),
        ("model-b", "V2"),
    ]


@pytest.mark.asyncio
@pytest.mark.nicegui_main_file("notebook_ta/bench/app.py")
async def test_compare_tab_renders_latest_results_as_an_aligned_matrix(user: User) -> None:
    """Each solution row must render beneath the same selected configuration headers."""
    state = _make_state_with_history()

    @ui.page("/")
    def page() -> None:
        """Render the comparison matrix under test."""
        build(state)

    await user.open("/")

    await user.should_see("Exercise / student solution")
    await user.should_see("model-a / V2 / 2026-02-01 00:00 UTC")
    await user.should_see("model-b / V2 / 2026-02-01 00:00 UTC")
    await user.should_see("Solution A")
    await user.should_see("Solution B")
    await user.should_see("answer = 1")
    await user.should_see("answer = 2")
    await user.should_see("Avg TTFT: 1.50s")
    await user.should_see("Avg Total: 2.50s")
    await user.should_see("Avg Speed: 15.00 tok/s")
    await user.should_see("V2 feedback for Solution A from model-a")
    await user.should_see("V2 feedback for Solution B from model-b")
    await user.should_not_see("V1 old feedback")
    correct_badge = next(
        badge for badge in user.find(ui.badge).elements if badge.text == "correct"
    )
    assert "#2E7D32" in str(correct_badge._style)
    assert correct_badge._props.get("color") != "primary"

    user.find("View exercise statement").click()
    await user.should_see("Complete exercise directions")


@pytest.mark.asyncio
@pytest.mark.nicegui_main_file("notebook_ta/bench/app.py")
async def test_run_deletion_requires_irreversible_action_confirmation(user: User) -> None:
    """Deleting a run must warn the user before cascading to its records."""
    state = _make_state_with_history()
    run = state.project.runs[-1]

    @ui.page("/")
    def page() -> None:
        """Render the deletion confirmation under test."""
        ui.button(
            "Request deletion",
            on_click=lambda: _open_delete_run_dialog(state, run, lambda: None),
        )

    await user.open("/")
    user.find("Request deletion").click()
    await user.should_see("This cannot be undone.")
    assert any(record.run_id == run.id for record in state.project.execution_records)

    user.find("Delete permanently").click()
    assert all(candidate.id != run.id for candidate in state.project.runs)
    assert all(record.run_id != run.id for record in state.project.execution_records)
