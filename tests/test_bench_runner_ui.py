"""Tests for benchmark runner UI progress helpers."""

from __future__ import annotations

from notebook_ta.bench.executor import BenchJob
from notebook_ta.bench.models import (
    BenchLLMConfig,
    ModelUnderTest,
    PromptVersion,
    StudentSolution,
)
from notebook_ta.bench.ui.runner_tab import (
    _finished_job_count,
    _initial_progress_rows,
    _is_deleted_ui_error,
    _job_key,
    _progress_row,
    _progress_value,
)
from notebook_ta.config.models import ExerciseConfig


def _make_job(
    exercise_id: str = "ex1",
    solution_label: str = "",
    model_label: str = "m1",
) -> BenchJob:
    return BenchJob(
        ExerciseConfig(id=exercise_id, statement="Example"),
        StudentSolution(exercise_id=exercise_id, label=solution_label, code="answer = 1"),
        ModelUnderTest(
            label=model_label,
            llm_config=BenchLLMConfig(
                provider="ollama",
                model="llama3.2:3b",
                base_url="http://localhost:11434",
            ),
        ),
        PromptVersion(id="V1", on_success="ok", on_failure="try again"),
    )


def test_progress_rows_are_seeded_for_full_run_total() -> None:
    jobs = [_make_job(model_label="m1"), _make_job(model_label="m2")]

    rows = _initial_progress_rows(jobs)

    assert len(rows) == 2
    assert {row["status"] for row in rows.values()} == {"queued"}
    assert _progress_value(rows, total_jobs=2) == 0


def test_progress_fraction_counts_finished_jobs_over_run_total() -> None:
    jobs = [_make_job(model_label="m1"), _make_job(model_label="m2")]
    rows = _initial_progress_rows(jobs)
    rows[_job_key(jobs[0])] = _progress_row(jobs[0], "completed")

    assert _finished_job_count(rows) == 1
    assert _progress_value(rows, total_jobs=2) == 0.5

    rows[_job_key(jobs[1])] = _progress_row(jobs[1], "failed", "boom")
    assert _finished_job_count(rows) == 2
    assert _progress_value(rows, total_jobs=2) == 1


def test_deleted_nicegui_client_errors_are_detected() -> None:
    assert _is_deleted_ui_error(
        RuntimeError("The client this element belongs to has been deleted.")
    )
    assert not _is_deleted_ui_error(RuntimeError("unrelated UI failure"))
