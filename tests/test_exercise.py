"""Tests for exercise prompt construction."""

from __future__ import annotations

import pytest

from notebook_ta.config.models import (
    ExerciseConfig,
    GlobalConfig,
    LLMConfig,
    PromptConfig,
    TestDefinition,
)
from notebook_ta.exercise.definition import Exercise, _SYSTEM_PREAMBLE
from notebook_ta.notebook.session import HintExchange
from notebook_ta.testing.runner import TestResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_global_config(**prompt_overrides) -> GlobalConfig:
    prompts = dict(
        on_success="Global success prompt.",
        on_failure="Global failure prompt.",
        on_no_llm="LLM unavailable.",
        hint_history_length=3,
    )
    prompts.update(prompt_overrides)
    return GlobalConfig(
        llm=LLMConfig(provider="ollama", model="llama3.2:3b", base_url="http://localhost:11434"),
        prompts=PromptConfig(**prompts),
    )


def make_exercise(
    exercise_id: str = "ex1",
    statement: str = "Write a function.",
    global_config: GlobalConfig | None = None,
    **ex_kwargs,
) -> Exercise:
    if global_config is None:
        global_config = make_global_config()
    cfg = ExerciseConfig(id=exercise_id, statement=statement, **ex_kwargs)
    return Exercise(config=cfg, global_config=global_config)


# ---------------------------------------------------------------------------
# Prompt context selection
# ---------------------------------------------------------------------------

class TestPromptContextSelection:
    def test_success_prompt_all_pass(self) -> None:
        ex = make_exercise()
        results = [TestResult(name="t", passed=True)]
        prompt = ex.build_prompt("def f(): pass", results, hint_history=None)
        assert "Global success prompt." in prompt

    def test_failure_prompt_any_fail(self) -> None:
        ex = make_exercise()
        results = [TestResult(name="t", passed=False)]
        prompt = ex.build_prompt("def f(): pass", results, hint_history=None)
        assert "Global failure prompt." in prompt

    def test_failure_prompt_when_history_present(self) -> None:
        ex = make_exercise()
        results = [TestResult(name="t", passed=False)]
        history = [HintExchange("code", "previous hint")]
        prompt = ex.build_prompt("def f(): pass", results, hint_history=history)
        assert "Global failure prompt." in prompt

    def test_exercise_level_overrides_global_success(self) -> None:
        ex = make_exercise(prompt_on_success="Exercise success prompt.")
        results = [TestResult(name="t", passed=True)]
        prompt = ex.build_prompt("def f(): pass", results)
        assert "Exercise success prompt." in prompt
        assert "Global success prompt." not in prompt

    def test_exercise_level_overrides_global_failure(self) -> None:
        ex = make_exercise(prompt_on_failure="Exercise failure prompt.")
        results = [TestResult(name="t", passed=False)]
        prompt = ex.build_prompt("def f(): pass", results)
        assert "Exercise failure prompt." in prompt

    def test_none_test_results_uses_success_prompt(self) -> None:
        ex = make_exercise()
        prompt = ex.build_prompt("code", test_results=None)
        assert "Global success prompt." in prompt


# ---------------------------------------------------------------------------
# Preamble and structural sections
# ---------------------------------------------------------------------------

class TestPromptSections:
    def test_preamble_always_present(self) -> None:
        ex = make_exercise()
        prompt = ex.build_prompt("code", [TestResult("t", True)])
        assert _SYSTEM_PREAMBLE in prompt

    def test_statement_always_in_prompt(self) -> None:
        ex = make_exercise(statement="Implement binary search.")
        prompt = ex.build_prompt("code", [TestResult("t", True)])
        assert "Implement binary search." in prompt

    def test_student_code_in_code_block(self) -> None:
        ex = make_exercise()
        prompt = ex.build_prompt("def add(a,b): return a+b", [TestResult("t", True)])
        assert "```python\ndef add(a,b): return a+b\n```" in prompt

    def test_optional_metadata_included_when_set(self) -> None:
        ex = make_exercise(
            additional_info="Use iteration.",
        )
        prompt = ex.build_prompt("code", [TestResult("t", True)])
        assert "Use iteration." in prompt

    def test_optional_metadata_absent_when_not_set(self) -> None:
        ex = make_exercise()
        prompt = ex.build_prompt("code", [TestResult("t", True)])
        assert "Additional Information" not in prompt

    def test_test_results_block_only_on_failure(self) -> None:
        ex = make_exercise()
        passing = [TestResult("t", True)]
        failing = [TestResult("t", False, "Wrong answer")]

        prompt_pass = ex.build_prompt("code", passing)
        prompt_fail = ex.build_prompt("code", failing)

        assert "Unit Test Results" not in prompt_pass
        assert "Unit Test Results" in prompt_fail
        assert "Wrong answer" in prompt_fail

    def test_hint_history_block_present_when_history_given(self) -> None:
        ex = make_exercise()
        history = [HintExchange("old_code", "first hint")]
        prompt = ex.build_prompt("new_code", [TestResult("t", False)], hint_history=history)
        assert "Previous Hint Exchanges" in prompt
        assert "first hint" in prompt

    def test_hint_history_block_absent_when_empty(self) -> None:
        ex = make_exercise()
        prompt = ex.build_prompt("code", [TestResult("t", False)], hint_history=[])
        assert "Previous Hint Exchanges" not in prompt

    def test_hint_history_truncated_to_max_length(self) -> None:
        global_cfg = make_global_config(hint_history_length=2)
        ex = make_exercise(global_config=global_cfg)
        history = [
            HintExchange("c1", "hint1"),
            HintExchange("c2", "hint2"),
            HintExchange("c3", "hint3"),
        ]
        prompt = ex.build_prompt("code", [TestResult("t", False)], hint_history=history)
        # Only last 2 should appear
        assert "hint3" in prompt
        assert "hint2" in prompt
        assert "hint1" not in prompt
