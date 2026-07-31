"""Tests for configured LLM answer postprocessors."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError

from notebook_ta.config.loader import load_global
from notebook_ta.config.models import AnswerPostprocessorConfig, ConfigurationError
from notebook_ta.llm.postprocessing import (
    LLMRequest,
    load_answer_postprocessor,
    postprocess_answer,
)


def make_request() -> LLMRequest:
    """Return a minimal request context for postprocessor tests."""
    return LLMRequest(
        call_type="analysis",
        exercise_id="ex1",
        prompt="Review this answer",
        student_code="answer = 42",
        test_results=(),
        hint_history=(),
        provider="ollama",
        model="test-model",
        temperature=0.3,
    )


def test_inline_postprocessor_loads_from_toml(tmp_path: Path) -> None:
    """The global TOML file should accept a multiline inline hook."""
    path = tmp_path / "global.toml"
    path.write_text(
        """
[llm]
model = "test"
base_url = "http://localhost:11434"

[prompts]
on_success = "Success"
on_failure = "Failure"
on_no_llm = "Unavailable"

[answer_postprocessor]
code = '''
def postprocess(request, answer, is_complete):
    return answer.upper()
'''
""",
        encoding="utf-8",
    )

    config = load_global(path)

    assert config.answer_postprocessor is not None
    assert "def postprocess" in (config.answer_postprocessor.code or "")


def test_inline_postprocessor_modifies_answer() -> None:
    """Inline code should resolve the required postprocess function."""
    hook = load_answer_postprocessor(
        AnswerPostprocessorConfig(
            code="""
def postprocess(request, answer, is_complete):
    state = "complete" if is_complete else "streaming"
    return f"{request.exercise_id} ({state}): {answer.replace('[score: 1]', '')}"
"""
        )
    )

    assert hook is not None
    result = asyncio.run(
        postprocess_answer(hook, make_request(), "Good [score: 1]", True)
    )

    assert result == "ex1 (complete): Good "


def test_external_async_postprocessor_modifies_answer() -> None:
    """External asynchronous callables should be imported and awaited."""
    module = ModuleType("test_course_hooks")

    async def transform(
        request: LLMRequest, answer: str, is_complete: bool
    ) -> str:
        return f"{request.call_type}/{is_complete}: {answer.upper()}"

    module.transform = transform  # type: ignore[attr-defined]
    sys.modules[module.__name__] = module
    try:
        hook = load_answer_postprocessor(
            AnswerPostprocessorConfig(module=module.__name__, function="transform")
        )
        assert hook is not None
        result = asyncio.run(postprocess_answer(hook, make_request(), "feedback", False))
    finally:
        del sys.modules[module.__name__]

    assert result == "analysis/False: FEEDBACK"


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"module": "hooks"},
        {"function": "transform"},
        {
            "code": "def postprocess(request, answer, is_complete): return answer",
            "module": "hooks",
            "function": "transform",
        },
    ],
)
def test_postprocessor_config_rejects_invalid_source_combinations(
    config: dict[str, str],
) -> None:
    """Exactly one complete postprocessor source must be configured."""
    with pytest.raises(ValidationError):
        AnswerPostprocessorConfig.model_validate(config)


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("this is not valid Python", "Failed to load"),
        ("postprocess = 42", "not callable"),
        ("def postprocess(request, answer): return answer", "must accept"),
    ],
)
def test_invalid_inline_postprocessor_fails_during_resolution(
    code: str, message: str
) -> None:
    """Broken inline hooks should be rejected before notebook execution."""
    with pytest.raises(ConfigurationError, match=message):
        load_answer_postprocessor(AnswerPostprocessorConfig(code=code))


@pytest.mark.parametrize("returned_value", [None, 123])
def test_invalid_runtime_result_falls_back_to_original_answer(
    returned_value: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Hook failures must preserve the unprocessed LLM answer."""
    def invalid_hook(
        _request: LLMRequest, _answer: str, _is_complete: bool
    ) -> object:
        return returned_value

    result = asyncio.run(
        postprocess_answer(  # type: ignore[arg-type]
            invalid_hook,
            make_request(),
            "original",
            False,
        )
    )

    assert result == "original"
    assert "using the original LLM answer" in caplog.text


def test_runtime_exception_falls_back_to_original_answer() -> None:
    """Exceptions raised by hooks must not hide otherwise valid LLM output."""
    def broken_hook(
        _request: LLMRequest, _answer: str, _is_complete: bool
    ) -> str:
        raise RuntimeError("broken")

    result = asyncio.run(
        postprocess_answer(broken_hook, make_request(), "original", True)
    )

    assert result == "original"


def test_runtime_failure_does_not_disable_later_updates() -> None:
    """A failed streaming invocation should not prevent the next hook invocation."""
    invocation = 0

    def flaky_hook(
        _request: LLMRequest, answer: str, is_complete: bool
    ) -> str:
        nonlocal invocation
        invocation += 1
        if invocation == 1:
            raise RuntimeError("temporary failure")
        return f"processed/{is_complete}: {answer}"

    request = make_request()
    first = asyncio.run(postprocess_answer(flaky_hook, request, "first", False))
    second = asyncio.run(
        postprocess_answer(flaky_hook, request, "first second", False)
    )

    assert first == "first"
    assert second == "processed/False: first second"
