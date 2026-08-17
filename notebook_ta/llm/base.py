"""Abstract LLM provider interface and factory function."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from notebook_ta.logging import get_logger

if TYPE_CHECKING:
    from notebook_ta.config.models import LLMConfig

_log = get_logger("llm")


@dataclass
class TokenUsage:
    """Token accounting for the most recently completed query()/stream() call."""

    prompt_tokens: int | None
    completion_tokens: int | None


@dataclass(frozen=True)
class LLMStreamChunk:
    """A categorized piece of a streaming LLM response."""

    kind: Literal["thinking", "answer"]
    content: str


class LLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    @abstractmethod
    async def query(self, prompt: str) -> str:
        """Send a prompt and return the full response string."""
        ...

    @abstractmethod
    def stream(self, prompt: str) -> AsyncIterator[str]:
        """Send a prompt and yield response chunks as they arrive."""
        ...

    async def stream_response(self, prompt: str) -> AsyncIterator[LLMStreamChunk]:
        """Yield categorized response chunks, defaulting to answer-only output.

        Providers whose backend separates thinking from the final answer override this
        method. The regular :meth:`stream` contract remains answer-only.
        """
        async for content in self.stream(prompt):
            yield LLMStreamChunk(kind="answer", content=content)

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the LLM backend is reachable."""
        ...

    @classmethod
    @abstractmethod
    def from_config(cls, config: LLMConfig) -> LLMProvider:
        """Construct an instance from a LLMConfig."""
        ...

    def get_last_usage(self) -> TokenUsage | None:
        """Return token usage for the most recently completed stream()/query() call.

        The default implementation returns None (unknown). Concrete providers that can
        obtain real token counts from the backend override this after each stream().
        """
        return None


def create_provider(config: LLMConfig) -> LLMProvider:
    """Factory: instantiate the correct LLMProvider based on config.provider.

    Args:
        config: Validated LLMConfig instance.

    Returns:
        A concrete LLMProvider instance.

    Raises:
        ValueError: For unknown provider names.
    """
    _log.debug("Creating LLM provider: %r (model=%r)", config.provider, config.model)
    if config.provider == "ollama":
        from notebook_ta.llm.ollama import OllamaProvider

        return OllamaProvider.from_config(config)
    elif config.provider == "openai_compat":
        from notebook_ta.llm.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider.from_config(config)
    else:
        raise ValueError(
            f"Unknown LLM provider: {config.provider!r}. "
            "Supported providers: 'ollama', 'openai_compat'."
        )
