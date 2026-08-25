"""Stale/drift detection hashing for the benchmarking tool.

Per the architecture decision, the drift hash covers the exercise `statement`,
`additional_info`, benchmark-only setup code, configured limits, the serialized unit
test definitions, and the student solution code.
A change to any of these marks a benchmark result as stale.
"""

from __future__ import annotations

import hashlib
import json

from notebook_ta.bench.models import ExecutionRecord, InputSnapshot, StudentSolution
from notebook_ta.config.models import ExerciseConfig, TestDefinition


def _hash(data: object) -> str:
    """Return a stable sha256 hex digest of a JSON-serializable structure."""
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _serialize_tests(tests: list[TestDefinition]) -> str:
    """Return a canonical JSON string for a list of TestDefinition."""
    return json.dumps([t.model_dump(mode="json") for t in tests], sort_keys=True, ensure_ascii=True)


def compute_exercise_hash(config: ExerciseConfig, setup_code: str | None = None) -> str:
    """Hash the exercise fields that affect the prompt and unit tests."""
    effective_setup_code = (
        (setup_code or None) if config.answer_type == "python" else None
    )
    payload = {
        "answer_type": config.answer_type,
        "statement": config.statement,
        "additional_info": config.additional_info,
        "evaluation_criteria": config.evaluation_criteria,
        "prompt_on_free_text": config.prompt_on_free_text,
        "setup_code": effective_setup_code,
        "unit_test_timeout": config.unit_test_timeout,
        "max_student_answer_length": config.max_student_answer_length,
        "max_unit_test_output_length": config.max_unit_test_output_length,
        "tests": _serialize_tests(config.tests),
    }
    return _hash(payload)


def compute_student_hash(code: str) -> str:
    """Hash the student solution source code."""
    return _hash({"code": code})


def build_input_snapshot(
    config: ExerciseConfig, solution: StudentSolution, setup_code: str | None = None
) -> InputSnapshot:
    """Capture a verbatim snapshot of the inputs used for a benchmark run, with drift hashes."""
    effective_setup_code = (
        (setup_code or None) if config.answer_type == "python" else None
    )
    exercise_hash = compute_exercise_hash(config, effective_setup_code)
    student_hash = compute_student_hash(solution.code)
    return InputSnapshot(
        exercise_statement=config.statement or "",
        additional_info=config.additional_info,
        setup_code=effective_setup_code,
        tests_serialized=_serialize_tests(config.tests),
        student_code=solution.code,
        exercise_hash=exercise_hash,
        student_hash=student_hash,
        combined_hash=_hash({"exercise": exercise_hash, "student": student_hash}),
        answer_type=config.answer_type,
        evaluation_criteria=config.evaluation_criteria,
    )


def is_stale(
    record: ExecutionRecord,
    live_config: ExerciseConfig,
    live_solution: StudentSolution,
    live_setup_code: str | None = None,
) -> bool:
    """Return True if the live exercise or solution has drifted from the record's snapshot."""
    live_exercise_hash = compute_exercise_hash(live_config, live_setup_code)
    live_student_hash = compute_student_hash(live_solution.code)
    return (
        live_exercise_hash != record.input_snapshot.exercise_hash
        or live_student_hash != record.input_snapshot.student_hash
    )
