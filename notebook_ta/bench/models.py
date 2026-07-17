"""Pydantic v2 data models for the prompt benchmarking tool.

The `BenchProject` model is the root object serialized to/from the benchmarking
project JSON file (see `notebook_ta.bench.storage.ProjectStore`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from re import fullmatch
from typing import Literal

from pydantic import BaseModel, Field

from notebook_ta.config.models import LLMConfig

DEFAULT_SOLUTION_TAGS = [
    "correct",
    "wrong complexity",
    "logic flow",
    "missing edge-case",
]
DEFAULT_TAG_COLOR = "#607D8B"
DEFAULT_TAG_COLORS = {
    "correct": "#2E7D32",
    "wrong complexity": "#EF6C00",
    "logic flow": "#1565C0",
    "missing edge-case": "#7B1FA2",
}


def _now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


def _new_id() -> str:
    """Return a new random UUID4 string."""
    return str(uuid.uuid4())


class BenchLLMConfig(LLMConfig):
    """Persistable LLM configuration containing a credential reference, never a secret."""


class BenchSettings(BaseModel):
    """Global settings for a benchmarking project."""

    internal_model: BenchLLMConfig
    unit_test_timeout: float = Field(default=5.0, gt=0)
    python_path_dirs: list[str] = []
    known_tags: list[str] = Field(default_factory=lambda: list(DEFAULT_SOLUTION_TAGS))
    tag_colors: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_TAG_COLORS))
    autosave_enabled: bool = True
    autosave_interval_seconds: int = Field(default=60, gt=0)
    exercises_toml_path: str | None = None

    def color_for_tag(self, tag: str) -> str:
        """Return the configured color for ``tag`` or the neutral fallback color."""
        color = self.tag_colors.get(tag, DEFAULT_TAG_COLOR)
        return color if fullmatch(r"#[0-9a-fA-F]{6}", color) else DEFAULT_TAG_COLOR


class StudentSolution(BaseModel):
    """A single student solution attached to an exercise."""

    id: str = Field(default_factory=_new_id)
    exercise_id: str
    label: str = ""
    code: str = ""
    tags: list[str] = []
    generated_by_internal_model: bool = False
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class PromptVersion(BaseModel):
    """A frozen (on_success, on_failure) prompt snapshot, assigned at "Run Benchmark" time."""

    id: str
    created_at: datetime = Field(default_factory=_now)
    on_success: str
    on_failure: str


class ModelUnderTest(BaseModel):
    """A model configuration selectable for benchmarking."""

    label: str
    llm_config: BenchLLMConfig


class BenchmarkRun(BaseModel):
    """A single "Run Benchmark" execution."""

    id: str = Field(default_factory=_new_id)
    name: str = ""
    prompt_version_id: str
    model_labels: list[str] = []
    job_count: int = 0
    status: Literal["running", "paused", "completed", "cancelled"] = "running"
    started_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None


class InputSnapshot(BaseModel):
    """Verbatim snapshot of the inputs used for one execution, plus drift hashes."""

    exercise_statement: str
    additional_info: str | None = None
    setup_code: str | None = None
    tests_serialized: str
    student_code: str
    exercise_hash: str
    student_hash: str
    combined_hash: str


class TokenUsage(BaseModel):
    """Token accounting for a single generation."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    approximate: bool = True


class ExecutionMetrics(BaseModel):
    """Performance metrics captured for a single generation."""

    time_to_first_token_s: float | None = None
    total_generation_time_s: float = 0.0
    throughput_tokens_per_s: float | None = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)


class TestResultModel(BaseModel):
    """Serializable mirror of `notebook_ta.testing.runner.TestResult`."""

    name: str
    passed: bool
    message: str | None = None


class ExecutionRecord(BaseModel):
    """The result of running one (exercise, solution, model, prompt version) job."""

    id: str = Field(default_factory=_new_id)
    run_id: str
    exercise_id: str
    solution_id: str
    model_label: str
    prompt_version_id: str
    input_snapshot: InputSnapshot
    full_prompt: str = ""
    test_results: list[TestResultModel] = []
    llm_output: str = ""
    metrics: ExecutionMetrics = Field(default_factory=ExecutionMetrics)
    status: Literal["completed", "failed"] = "completed"
    error: str | None = None
    created_at: datetime = Field(default_factory=_now)


class BenchProject(BaseModel):
    """Root object serialized to/from the benchmarking project JSON file."""

    schema_version: int = 2
    settings: BenchSettings
    draft_prompt_on_success: str = ""
    draft_prompt_on_failure: str = ""
    draft_selected_model_labels: list[str] = []
    draft_run_name: str = ""
    setup_code_by_exercise: dict[str, str] = Field(default_factory=dict)
    solutions: list[StudentSolution] = []
    prompt_versions: list[PromptVersion] = []
    models_under_test: list[ModelUnderTest] = []
    runs: list[BenchmarkRun] = []
    execution_records: list[ExecutionRecord] = []

    def next_prompt_version_id(self) -> str:
        """Return the next sequential prompt version label, e.g. 'V1', 'V2', ..."""
        return f"V{len(self.prompt_versions) + 1}"

    def solutions_for(self, exercise_id: str) -> list[StudentSolution]:
        """Return all student solutions attached to the given exercise."""
        return [s for s in self.solutions if s.exercise_id == exercise_id]

    def setup_code_for(self, exercise_id: str) -> str:
        """Return benchmark-only setup code configured for ``exercise_id``."""
        return self.setup_code_by_exercise.get(exercise_id, "")

    def latest_record(
        self, exercise_id: str, solution_id: str, model_label: str, prompt_version_id: str
    ) -> ExecutionRecord | None:
        """Return the most recent ExecutionRecord matching the given combination, if any."""
        matches = [
            r
            for r in self.execution_records
            if r.exercise_id == exercise_id
            and r.solution_id == solution_id
            and r.model_label == model_label
            and r.prompt_version_id == prompt_version_id
        ]
        if not matches:
            return None
        return max(matches, key=lambda r: r.created_at)

    def known_combinations(self, exercise_id: str, solution_id: str) -> list[tuple[str, str]]:
        """Return all distinct (model_label, prompt_version_id) combos run for this context."""
        seen: dict[tuple[str, str], None] = {}
        for r in self.execution_records:
            if r.exercise_id == exercise_id and r.solution_id == solution_id:
                seen[(r.model_label, r.prompt_version_id)] = None
        return list(seen.keys())


class BenchProjectError(Exception):
    """Raised when a benchmarking project file fails to load or validate."""
