"""Tests for notebook_ta.bench.hashing (stale/drift detection)."""

from __future__ import annotations

from notebook_ta.bench.hashing import (
    build_input_snapshot,
    compute_exercise_hash,
    compute_student_hash,
    is_stale,
)
from notebook_ta.bench.models import StudentSolution
from notebook_ta.config.models import ExerciseConfig, TestDefinition


def make_exercise(**overrides) -> ExerciseConfig:
    defaults = dict(id="ex1", statement="Write a function that adds two numbers.")
    defaults.update(overrides)
    return ExerciseConfig(**defaults)


def make_solution(code: str = "def add(a, b): return a + b") -> StudentSolution:
    return StudentSolution(exercise_id="ex1", code=code)


class TestHashStability:
    def test_same_inputs_produce_same_hash(self) -> None:
        config = make_exercise()
        assert compute_exercise_hash(config) == compute_exercise_hash(make_exercise())

    def test_statement_change_changes_hash(self) -> None:
        original = compute_exercise_hash(make_exercise())
        changed = compute_exercise_hash(make_exercise(statement="A different statement."))
        assert original != changed

    def test_additional_info_change_changes_hash(self) -> None:
        original = compute_exercise_hash(make_exercise())
        changed = compute_exercise_hash(make_exercise(additional_info="Use recursion."))
        assert original != changed

    def test_setup_code_change_changes_hash(self) -> None:
        original = compute_exercise_hash(make_exercise())
        changed = compute_exercise_hash(make_exercise(), setup_code="expected = 5")
        assert original != changed

    def test_test_definitions_change_changes_hash(self) -> None:
        original = compute_exercise_hash(make_exercise())
        changed = compute_exercise_hash(
            make_exercise(tests=[TestDefinition(name="t1", code="def t(): return True")])
        )
        assert original != changed

    def test_student_code_change_changes_hash(self) -> None:
        assert compute_student_hash("a") != compute_student_hash("b")

    def test_student_hash_unaffected_by_exercise(self) -> None:
        assert compute_student_hash("same code") == compute_student_hash("same code")


class TestInputSnapshot:
    def test_snapshot_captures_verbatim_fields(self) -> None:
        config = make_exercise(additional_info="info")
        solution = make_solution()
        snapshot = build_input_snapshot(config, solution, setup_code="expected = 5")
        assert snapshot.exercise_statement == config.statement
        assert snapshot.additional_info == "info"
        assert snapshot.setup_code == "expected = 5"
        assert snapshot.student_code == solution.code
        assert snapshot.combined_hash


class TestIsStale:
    def test_not_stale_when_nothing_changed(self) -> None:
        config = make_exercise()
        solution = make_solution()
        snapshot = build_input_snapshot(config, solution)
        record = ExecutionRecordStub(snapshot)
        assert is_stale(record, config, solution) is False

    def test_stale_when_exercise_statement_changes(self) -> None:
        config = make_exercise()
        solution = make_solution()
        snapshot = build_input_snapshot(config, solution)
        record = ExecutionRecordStub(snapshot)
        drifted_config = make_exercise(statement="Changed statement.")
        assert is_stale(record, drifted_config, solution) is True

    def test_stale_when_student_code_changes(self) -> None:
        config = make_exercise()
        solution = make_solution()
        snapshot = build_input_snapshot(config, solution)
        record = ExecutionRecordStub(snapshot)
        drifted_solution = make_solution(code="def add(a, b): return a - b")
        assert is_stale(record, config, drifted_solution) is True

    def test_stale_when_setup_code_changes(self) -> None:
        config = make_exercise()
        solution = make_solution()
        snapshot = build_input_snapshot(config, solution, setup_code="expected = 5")
        record = ExecutionRecordStub(snapshot)
        assert is_stale(record, config, solution, live_setup_code="expected = 6") is True


class ExecutionRecordStub:
    """Minimal stand-in exposing only the `input_snapshot` attribute `is_stale()` needs."""

    def __init__(self, input_snapshot) -> None:
        self.input_snapshot = input_snapshot
