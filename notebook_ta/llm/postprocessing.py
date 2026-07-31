"""Configuration and execution support for LLM answer postprocessors."""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, cast

from notebook_ta.config.models import AnswerPostprocessorConfig, ConfigurationError
from notebook_ta.logging import get_logger

if TYPE_CHECKING:
    from notebook_ta.notebook.session import HintExchange
    from notebook_ta.testing.runner import TestResult

_log = get_logger("llm.postprocessing")


@dataclass(frozen=True)
class LLMRequest:
    """Parameters and notebook context associated with an LLM request."""

    call_type: Literal["analysis", "hint"]
    exercise_id: str
    prompt: str
    student_code: str
    test_results: tuple[TestResult, ...]
    hint_history: tuple[HintExchange, ...]
    provider: str
    model: str
    temperature: float


AnswerPostprocessor: TypeAlias = Callable[  # noqa: UP040 - Python 3.11 support
    [LLMRequest, str, bool], str | Awaitable[str]
]


def load_answer_postprocessor(
    config: AnswerPostprocessorConfig | None,
) -> AnswerPostprocessor | None:
    """Resolve and validate an answer postprocessor from configuration.

    Inline code must define ``postprocess(request, answer, is_complete)``. External hooks are
    imported using their configured module and function names.

    Args:
        config: Validated hook configuration, or ``None`` when disabled.

    Returns:
        The resolved callable, or ``None``.

    Raises:
        ConfigurationError: If code cannot be compiled, imported, or resolved to
            a callable accepting three positional arguments.
    """
    if config is None:
        return None

    try:
        if config.code is not None:
            namespace: dict[str, Any] = {}
            exec(compile(config.code, "<answer_postprocessor>", "exec"), namespace)
            candidate = namespace.get("postprocess")
            source = "inline answer_postprocessor.postprocess"
        else:
            assert config.module is not None
            assert config.function is not None
            module = importlib.import_module(config.module)
            candidate = getattr(module, config.function)
            source = f"{config.module}.{config.function}"
    except Exception as exc:
        raise ConfigurationError(f"Failed to load answer postprocessor: {exc}") from exc

    if not callable(candidate):
        raise ConfigurationError(f"Answer postprocessor {source!r} is not callable.")

    try:
        inspect.signature(candidate).bind(object(), "answer", False)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(
            f"Answer postprocessor {source!r} must accept "
            "(request, answer, is_complete)."
        ) from exc
    return cast(AnswerPostprocessor, candidate)


async def postprocess_answer(
    postprocessor: AnswerPostprocessor,
    request: LLMRequest,
    answer: str,
    is_complete: bool,
) -> str:
    """Run a hook update, falling back to the accumulated raw answer on failure."""
    try:
        result = postprocessor(request, answer, is_complete)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, str):
            raise TypeError(
                "answer postprocessor must return str, "
                f"got {type(result).__name__}"
            )
        return result
    except Exception as exc:
        _log.warning("Answer postprocessor failed; using the original LLM answer: %s", exc)
        return answer
