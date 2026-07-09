"""Sequential benchmark execution engine with per-job metrics capture.

Per the architecture decision, LLM calls are processed strictly one at a time
across the whole exercise x solution x model matrix -- this keeps hardware load
predictable and keeps TTFT/throughput measurements free of interference from
concurrent requests.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from notebook_ta.bench.hashing import build_input_snapshot
from notebook_ta.bench.models import (
    BenchmarkRun,
    ExecutionMetrics,
    ExecutionRecord,
    ModelUnderTest,
    PromptVersion,
    StudentSolution,
    TestResultModel,
    TokenUsage,
)
from notebook_ta.config.models import ExerciseConfig, GlobalConfig, PromptConfig
from notebook_ta.exercise.definition import Exercise
from notebook_ta.llm.base import LLMProvider, create_provider
from notebook_ta.logging import get_logger
from notebook_ta.testing.runner import TestResult, TestRunner

_log = get_logger("bench.executor")


@dataclass
class BenchJob:
    """One (exercise, solution, model, prompt version) unit of work for a benchmark run."""

    exercise_config: ExerciseConfig
    solution: StudentSolution
    model: ModelUnderTest
    prompt_version: PromptVersion
    setup_code: str = ""


# Called as on_progress(job, status, message, record). `record` is populated only
# when the job has just finished (status in {"completed", "failed"}).
ProgressCallback = Callable[[BenchJob, str, "str | None", "ExecutionRecord | None"], None]


@contextmanager
def extended_sys_path(dirs: list[str]) -> Iterator[None]:
    """Temporarily prepend `dirs` to `sys.path` for external test module imports."""
    added = [d for d in dirs if d not in sys.path]
    for d in added:
        sys.path.insert(0, d)
    try:
        yield
    finally:
        for d in added:
            if d in sys.path:
                sys.path.remove(d)


def _build_global_config(prompt_version: PromptVersion, model: ModelUnderTest) -> GlobalConfig:
    """Build a synthetic GlobalConfig so `Exercise.build_prompt()` can be reused unchanged."""
    return GlobalConfig(
        llm=model.llm_config,
        prompts=PromptConfig(
            on_success=prompt_version.on_success,
            on_failure=prompt_version.on_failure,
            on_no_llm="",
        ),
    )


def build_jobs(
    exercises: list[ExerciseConfig],
    solutions_by_exercise: dict[str, list[StudentSolution]],
    models: list[ModelUnderTest],
    prompt_version: PromptVersion,
    setup_code_by_exercise: dict[str, str] | None = None,
) -> list[BenchJob]:
    """Build the full model x exercise x solution job matrix for a benchmark run.

    Jobs are grouped by model first (outer loop) so that `BenchExecutor.run()` -- which
    processes the list strictly in order -- finishes every job for one model before moving
    to the next. This avoids repeatedly loading/unloading models on the LLM backend (e.g.
    Ollama swapping models in and out of GPU/RAM) that would happen with an exercise-major
    ordering.
    """
    setup_code_by_exercise = setup_code_by_exercise or {}
    jobs: list[BenchJob] = []
    for model in models:
        for exercise_config in exercises:
            for solution in solutions_by_exercise.get(exercise_config.id, []):
                jobs.append(
                    BenchJob(
                        exercise_config,
                        solution,
                        model,
                        prompt_version,
                        setup_code_by_exercise.get(exercise_config.id, ""),
                    )
                )
    return jobs


def run_setup_code(
    setup_code: str, namespace: dict[str, object], test_names: list[str]
) -> list[TestResult] | None:
    """Run benchmark setup code and return failed test results if setup fails."""
    if not setup_code:
        return None
    stdout_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buf):
            exec(setup_code, namespace)  # noqa: S102 -- isolated authoring-time sandbox
    except Exception as exc:
        captured = stdout_buf.getvalue()
        message = str(exc)
        if captured:
            message = f"{message}\nOutput: {captured}"
        return [
            TestResult(name=name, passed=False, message=f"Setup code failed: {message}")
            for name in test_names
        ]
    return None


class BenchExecutor:
    """Runs a benchmark job matrix sequentially, one LLM call at a time."""

    def __init__(
        self,
        python_path_dirs: Callable[[], list[str]] | None = None,
        unit_test_timeout: Callable[[], float] | None = None,
    ) -> None:
        """`python_path_dirs`, if given, is called fresh before every job so that changes
        made in the Settings tab while a run is in progress take effect immediately."""
        self._get_python_path_dirs = python_path_dirs or (lambda: [])
        self._get_unit_test_timeout = unit_test_timeout or (lambda: 5.0)
        self._provider_cache: dict[str, LLMProvider] = {}
        self._cancel_requested = False
        self._retry_event: asyncio.Event | None = None

    def cancel(self) -> None:
        """Request cancellation; takes effect before the next job starts (or on retry-wait)."""
        self._cancel_requested = True
        if self._retry_event is not None:
            self._retry_event.set()

    def retry(self) -> None:
        """Resume a paused run (e.g. after the user restarts a disconnected LLM server)."""
        if self._retry_event is not None:
            self._retry_event.set()

    def _get_provider(self, model: ModelUnderTest) -> LLMProvider:
        """Return a cached LLMProvider instance for `model`, creating one if needed."""
        if model.label not in self._provider_cache:
            self._provider_cache[model.label] = create_provider(model.llm_config)
        return self._provider_cache[model.label]

    async def run(
        self, jobs: list[BenchJob], run: BenchmarkRun, on_progress: ProgressCallback
    ) -> None:
        """Execute all jobs sequentially, invoking `on_progress` as progress is made."""
        self._cancel_requested = False
        for job in jobs:
            if self._cancel_requested:
                run.status = "cancelled"
                return

            provider = self._get_provider(job.model)
            while not provider.is_available():
                run.status = "paused"
                on_progress(job, "paused", f"{job.model.label} is unreachable", None)
                self._retry_event = asyncio.Event()
                await self._retry_event.wait()
                if self._cancel_requested:
                    run.status = "cancelled"
                    return
            run.status = "running"

            await self._execute_job(job, run, on_progress)

        if run.status == "running":
            run.status = "completed"

    async def run_single(self, job: BenchJob, run: BenchmarkRun) -> ExecutionRecord:
        """Execute a single job immediately, bypassing the queue (used for a Compare tab Re-run)."""
        record_box: list[ExecutionRecord] = []

        def _capture(
            _job: BenchJob,
            _status: str,
            _message: str | None,
            record: ExecutionRecord | None,
        ) -> None:
            if record is not None:
                record_box.append(record)

        await self._execute_job(job, run, _capture)
        return record_box[0]

    async def _execute_job(
        self, job: BenchJob, run: BenchmarkRun, on_progress: ProgressCallback
    ) -> None:
        """Run unit tests + the LLM call for one job and report the resulting record."""
        on_progress(job, "generating", None, None)
        snapshot = build_input_snapshot(job.exercise_config, job.solution, job.setup_code)
        global_config = _build_global_config(job.prompt_version, job.model)
        global_config.unit_test_timeout = self._get_unit_test_timeout()
        exercise = Exercise(job.exercise_config, global_config)

        try:
            namespace: dict[str, object] = {}
            with extended_sys_path(self._get_python_path_dirs()):
                exec(job.solution.code, namespace)  # noqa: S102 -- isolated authoring-time sandbox
                test_names = [test_def.name for test_def in exercise.tests]
                test_results = run_setup_code(job.setup_code, namespace, test_names)
                if test_results is None:
                    test_results = TestRunner().run(exercise, namespace)
            prompt = exercise.build_prompt(job.solution.code, test_results, hint_history=None)

            provider = self._get_provider(job.model)
            output, metrics = await self._run_llm(provider, prompt)

            record = ExecutionRecord(
                run_id=run.id,
                exercise_id=job.exercise_config.id,
                solution_id=job.solution.id,
                model_label=job.model.label,
                prompt_version_id=job.prompt_version.id,
                input_snapshot=snapshot,
                full_prompt=prompt,
                test_results=[
                    TestResultModel(name=r.name, passed=r.passed, message=r.message)
                    for r in test_results
                ],
                llm_output=output,
                metrics=metrics,
                status="completed",
            )
            on_progress(job, "completed", None, record)
        except Exception as exc:
            _log.warning(
                "Job failed for exercise=%r solution=%r model=%r: %s",
                job.exercise_config.id,
                job.solution.id,
                job.model.label,
                exc,
            )
            record = ExecutionRecord(
                run_id=run.id,
                exercise_id=job.exercise_config.id,
                solution_id=job.solution.id,
                model_label=job.model.label,
                prompt_version_id=job.prompt_version.id,
                input_snapshot=snapshot,
                status="failed",
                error=str(exc),
            )
            on_progress(job, "failed", str(exc), record)

    @staticmethod
    async def _run_llm(provider: LLMProvider, prompt: str) -> tuple[str, ExecutionMetrics]:
        """Stream `prompt` through `provider`, timing TTFT/total time and capturing token usage."""
        start = time.monotonic()
        first_token_time: float | None = None
        chunks: list[str] = []
        async for chunk in provider.stream(prompt):
            if first_token_time is None:
                first_token_time = time.monotonic()
            chunks.append(chunk)
        end = time.monotonic()
        output = "".join(chunks)

        usage = provider.get_last_usage()
        if usage and usage.completion_tokens:
            completion_tokens = usage.completion_tokens
            prompt_tokens = usage.prompt_tokens
            approximate = False
        else:
            completion_tokens = len(output.split())
            prompt_tokens = usage.prompt_tokens if usage else None
            approximate = True

        total_time = end - start
        ttft = (first_token_time - start) if first_token_time is not None else None
        throughput = (completion_tokens / total_time) if total_time > 0 else None

        return output, ExecutionMetrics(
            time_to_first_token_s=ttft,
            total_generation_time_s=total_time,
            throughput_tokens_per_s=throughput,
            token_usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                approximate=approximate,
            ),
        )
