"""Tests for notebook_ta.bench.executor (sequential scheduling + metrics)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from notebook_ta.bench.executor import BenchExecutor, BenchJob, build_jobs
from notebook_ta.bench.models import BenchmarkRun, ModelUnderTest, PromptVersion, StudentSolution
from notebook_ta.config.models import ExerciseConfig, LLMConfig, TestDefinition
from notebook_ta.llm.base import LLMProvider, TokenUsage


class FakeProvider(LLMProvider):
    """A minimal LLMProvider stand-in for deterministic executor tests."""

    def __init__(
        self,
        chunks: list[str],
        available: bool = True,
        usage: TokenUsage | None = None,
    ) -> None:
        self.chunks = chunks
        self._available = available
        self._usage = usage
        self.call_count = 0

    @classmethod
    def from_config(cls, config: LLMConfig) -> FakeProvider:  # pragma: no cover - unused
        return cls([])

    def is_available(self) -> bool:
        return self._available

    async def query(self, prompt: str) -> str:  # pragma: no cover - unused
        return "".join(self.chunks)

    async def stream(self, prompt: str):
        self.call_count += 1
        for chunk in self.chunks:
            yield chunk

    def get_last_usage(self) -> TokenUsage | None:
        return self._usage


def make_exercise(
    exercise_id: str = "ex1", tests: list[TestDefinition] | None = None
) -> ExerciseConfig:
    return ExerciseConfig(
        id=exercise_id,
        statement="Write add(a, b).",
        tests=tests
        or [TestDefinition(name="adds", code="def adds(add): return add(2, 3) == 5")],
    )


def make_solution(
    exercise_id: str = "ex1", code: str = "def add(a, b): return a + b"
) -> StudentSolution:
    return StudentSolution(exercise_id=exercise_id, code=code)


def make_model(label: str = "m1") -> ModelUnderTest:
    return ModelUnderTest(
        label=label,
        llm_config=LLMConfig(provider="ollama", model="llama3.2:3b", base_url="http://localhost:11434"),
    )


def make_prompt_version() -> PromptVersion:
    return PromptVersion(id="V1", on_success="Great job!", on_failure="Keep trying.")


class TestBuildJobs:
    def test_matrix_covers_all_combinations(self) -> None:
        exercises = [make_exercise("ex1"), make_exercise("ex2")]
        solutions_by_exercise = {
            "ex1": [make_solution("ex1")],
            "ex2": [make_solution("ex2"), make_solution("ex2")],
        }
        models = [make_model("m1"), make_model("m2")]
        jobs = build_jobs(exercises, solutions_by_exercise, models, make_prompt_version())
        assert len(jobs) == (1 * 2) + (2 * 2)

    def test_exercise_without_solutions_produces_no_jobs(self) -> None:
        exercises = [make_exercise("ex1")]
        jobs = build_jobs(exercises, {}, [make_model()], make_prompt_version())
        assert jobs == []

    def test_jobs_are_grouped_model_major(self) -> None:
        """All jobs for one model must come before any job for the next model, so the
        executor finishes with one model before switching (avoids reload churn)."""
        exercises = [make_exercise("ex1"), make_exercise("ex2")]
        solutions_by_exercise = {
            "ex1": [make_solution("ex1")],
            "ex2": [make_solution("ex2")],
        }
        models = [make_model("m1"), make_model("m2")]
        jobs = build_jobs(exercises, solutions_by_exercise, models, make_prompt_version())
        model_labels_in_order = [job.model.label for job in jobs]
        assert model_labels_in_order == ["m1", "m1", "m2", "m2"]


class TestBenchExecutorSequential:
    @pytest.mark.asyncio
    async def test_jobs_run_one_at_a_time_and_complete(self) -> None:
        config = make_exercise()
        job1 = BenchJob(config, make_solution(), make_model("m1"), make_prompt_version())
        job2 = BenchJob(config, make_solution(), make_model("m2"), make_prompt_version())

        providers = {
            "m1": FakeProvider(["Hello", " there"]),
            "m2": FakeProvider(["Second", " model"]),
        }
        call_order: list[str] = ["m1", "m2"]

        def _create(llm_config: LLMConfig):
            return providers[call_order.pop(0)]

        events: list[tuple[str, str]] = []

        def on_progress(job, status, message, record) -> None:
            events.append((job.model.label, status))

        run = BenchmarkRun(prompt_version_id="V1", model_labels=["m1", "m2"], job_count=2)
        executor = BenchExecutor()
        with patch("notebook_ta.bench.executor.create_provider", side_effect=_create):
            await executor.run([job1, job2], run, on_progress)

        assert run.status == "completed"
        statuses = [e for e in events if e[1] == "completed"]
        assert len(statuses) == 2
        assert providers["m1"].call_count == 1
        assert providers["m2"].call_count == 1

    @pytest.mark.asyncio
    async def test_pause_and_retry_on_unavailable_provider(self) -> None:
        config = make_exercise()
        job = BenchJob(config, make_solution(), make_model("m1"), make_prompt_version())
        provider = FakeProvider(["Hi"], available=False)

        run = BenchmarkRun(prompt_version_id="V1", model_labels=["m1"], job_count=1)
        executor = BenchExecutor()
        statuses: list[str] = []

        def on_progress(job, status, message, record) -> None:
            statuses.append(status)

        async def _flip_available_and_retry() -> None:
            await asyncio.sleep(0.05)
            provider._available = True
            executor.retry()

        with patch("notebook_ta.bench.executor.create_provider", return_value=provider):
            await asyncio.gather(executor.run([job], run, on_progress), _flip_available_and_retry())

        assert "paused" in statuses
        assert run.status == "completed"

    @pytest.mark.asyncio
    async def test_job_failure_is_isolated_and_run_continues(self) -> None:
        config = make_exercise()
        good_solution = make_solution(code="def add(a, b): return a + b")
        bad_solution = make_solution(code="this is not valid python (((")
        job_bad = BenchJob(config, bad_solution, make_model("m1"), make_prompt_version())
        job_good = BenchJob(config, good_solution, make_model("m1"), make_prompt_version())
        provider = FakeProvider(["ok"])

        run = BenchmarkRun(prompt_version_id="V1", model_labels=["m1"], job_count=2)
        executor = BenchExecutor()
        records = []

        def on_progress(job, status, message, record) -> None:
            if record is not None:
                records.append(record)

        with patch("notebook_ta.bench.executor.create_provider", return_value=provider):
            await executor.run([job_bad, job_good], run, on_progress)

        assert run.status == "completed"
        assert len(records) == 2
        assert records[0].status == "failed"
        assert records[0].error is not None
        assert records[1].status == "completed"

    @pytest.mark.asyncio
    async def test_solution_execution_timeout_is_reported_as_failed_test(self) -> None:
        config = make_exercise()
        solution = make_solution(
            code="""\
while True:
    pass
"""
        )
        job = BenchJob(config, solution, make_model("m1"), make_prompt_version())
        provider = FakeProvider(["ok"])

        run = BenchmarkRun(prompt_version_id="V1", model_labels=["m1"], job_count=1)
        executor = BenchExecutor(unit_test_timeout=lambda: 0.2)
        records = []

        def on_progress(job, status, message, record) -> None:
            if record is not None:
                records.append(record)

        with patch("notebook_ta.bench.executor.create_provider", return_value=provider):
            await executor.run([job], run, on_progress)

        assert records[0].status == "completed"
        assert records[0].test_results[0].passed is False
        assert "timed out after 0.2 seconds" in (records[0].test_results[0].message or "")

    @pytest.mark.asyncio
    async def test_metrics_use_word_count_fallback_without_usage(self) -> None:
        config = make_exercise()
        job = BenchJob(config, make_solution(), make_model("m1"), make_prompt_version())
        provider = FakeProvider(["four words here now"], usage=None)

        run = BenchmarkRun(prompt_version_id="V1", model_labels=["m1"], job_count=1)
        executor = BenchExecutor()
        records = []

        def on_progress(job, status, message, record) -> None:
            if record is not None:
                records.append(record)

        with patch("notebook_ta.bench.executor.create_provider", return_value=provider):
            await executor.run([job], run, on_progress)

        record = records[0]
        assert record.metrics.token_usage.approximate is True
        assert record.metrics.token_usage.completion_tokens == 4

    @pytest.mark.asyncio
    async def test_metrics_use_provider_usage_when_available(self) -> None:
        config = make_exercise()
        job = BenchJob(config, make_solution(), make_model("m1"), make_prompt_version())
        provider = FakeProvider(["hi"], usage=TokenUsage(prompt_tokens=10, completion_tokens=3))

        run = BenchmarkRun(prompt_version_id="V1", model_labels=["m1"], job_count=1)
        executor = BenchExecutor()
        records = []

        def on_progress(job, status, message, record) -> None:
            if record is not None:
                records.append(record)

        with patch("notebook_ta.bench.executor.create_provider", return_value=provider):
            await executor.run([job], run, on_progress)

        record = records[0]
        assert record.metrics.token_usage.approximate is False
        assert record.metrics.token_usage.completion_tokens == 3
        assert record.metrics.token_usage.prompt_tokens == 10

    @pytest.mark.asyncio
    async def test_benchmark_unit_test_timeout_is_recorded_and_prompted(self) -> None:
        config = make_exercise(
            tests=[
                TestDefinition(
                    name="slow",
                    code="""\
def slow(add):
    import time
    time.sleep(2)
    return True
""",
                )
            ]
        )
        job = BenchJob(config, make_solution(), make_model("m1"), make_prompt_version())
        provider = FakeProvider(["ok"])

        run = BenchmarkRun(prompt_version_id="V1", model_labels=["m1"], job_count=1)
        executor = BenchExecutor(unit_test_timeout=lambda: 0.2)
        records = []

        def on_progress(job, status, message, record) -> None:
            if record is not None:
                records.append(record)

        with patch("notebook_ta.bench.executor.create_provider", return_value=provider):
            await executor.run([job], run, on_progress)

        record = records[0]
        message = record.test_results[0].message or ""
        assert record.test_results[0].passed is False
        assert "timed out after 0.2 seconds" in message
        assert "timed out after 0.2 seconds" in record.full_prompt

    @pytest.mark.asyncio
    async def test_benchmark_setup_code_definitions_are_available_to_tests(self) -> None:
        config = make_exercise(
            tests=[
                TestDefinition(
                    name="uses setup value",
                    code="def check(add, expected): return add(2, 3) == expected",
                )
            ]
        )
        job = BenchJob(
            config,
            make_solution(),
            make_model("m1"),
            make_prompt_version(),
            "expected = 5",
        )
        provider = FakeProvider(["ok"])
        run = BenchmarkRun(prompt_version_id="V1", model_labels=["m1"], job_count=1)
        executor = BenchExecutor()
        records = []

        def on_progress(job, status, message, record) -> None:
            if record is not None:
                records.append(record)

        with patch("notebook_ta.bench.executor.create_provider", return_value=provider):
            await executor.run([job], run, on_progress)

        assert records[0].status == "completed"
        assert records[0].test_results[0].passed is True
        assert records[0].input_snapshot.setup_code == "expected = 5"

    @pytest.mark.asyncio
    async def test_benchmark_setup_code_failure_becomes_failed_test_result(self) -> None:
        config = make_exercise()
        job = BenchJob(
            config,
            make_solution(),
            make_model("m1"),
            make_prompt_version(),
            'raise RuntimeError("setup boom")',
        )
        provider = FakeProvider(["ok"])
        run = BenchmarkRun(prompt_version_id="V1", model_labels=["m1"], job_count=1)
        executor = BenchExecutor()
        records = []

        def on_progress(job, status, message, record) -> None:
            if record is not None:
                records.append(record)

        with patch("notebook_ta.bench.executor.create_provider", return_value=provider):
            await executor.run([job], run, on_progress)

        assert records[0].status == "completed"
        assert records[0].test_results[0].passed is False
        assert "setup boom" in (records[0].test_results[0].message or "")


class TestBenchExecutorPythonPath:
    @pytest.mark.asyncio
    async def test_python_path_dirs_are_read_live(self, tmp_path) -> None:
        """Changing the underlying list after BenchExecutor construction (e.g. editing
        it in the Settings tab) must still be picked up by subsequent job runs."""
        (tmp_path / "bench_pythonpath_test_helper.py").write_text(
            "def check_add(add):\n    return add(2, 3) == 5\n", encoding="utf-8"
        )
        config = make_exercise(
            tests=[
                TestDefinition(
                    name="via external module",
                    module="bench_pythonpath_test_helper",
                    function="check_add",
                )
            ]
        )
        job = BenchJob(config, make_solution(), make_model("m1"), make_prompt_version())
        provider = FakeProvider(["ok"])
        run = BenchmarkRun(prompt_version_id="V1", model_labels=["m1"], job_count=1)

        dirs: list[str] = []  # empty at BenchExecutor construction time
        executor = BenchExecutor(lambda: dirs)
        dirs.append(str(tmp_path))  # simulate a later Settings-tab edit

        records = []

        def on_progress(job, status, message, record) -> None:
            if record is not None:
                records.append(record)

        with patch("notebook_ta.bench.executor.create_provider", return_value=provider):
            await executor.run([job], run, on_progress)

        assert records[0].status == "completed"
        assert records[0].test_results[0].passed is True
