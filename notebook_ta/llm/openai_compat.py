"""OpenAI-compatible LLM provider implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator

from notebook_ta.llm.base import LLMProvider, TokenUsage
from notebook_ta.logging import get_logger

if TYPE_CHECKING:
    from notebook_ta.config.models import LLMConfig

_log = get_logger("llm.openai")


class OpenAICompatProvider(LLMProvider):
    """LLM provider for OpenAI-compatible APIs (LM Studio, vLLM, Ollama OpenAI endpoint, etc.)."""

    def __init__(
        self, base_url: str, api_key: str | None, model: str, timeout: int, temperature: float = 0.7
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key or "not-set"
        self._model = model
        self._timeout = timeout
        self._temperature = temperature
        self._last_usage: TokenUsage | None = None

    @classmethod
    def from_config(cls, config: "LLMConfig") -> "OpenAICompatProvider":
        return cls(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            timeout=config.timeout,
            temperature=config.temperature,
        )

    def _get_client(self):  # type: ignore[no-untyped-def]
        from openai import AsyncOpenAI

        return AsyncOpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
            timeout=float(self._timeout),
        )

    def is_available(self) -> bool:
        """Return True if the OpenAI-compatible server responds to a models list request."""
        import asyncio

        from openai import AsyncOpenAI, OpenAIError

        async def _check() -> bool:
            client = AsyncOpenAI(
                base_url=self._base_url,
                api_key=self._api_key,
                timeout=5.0,
            )
            try:
                await client.models.list()
                return True
            except OpenAIError:
                _log.warning("OpenAI-compat server not reachable at %r", self._base_url)
                return False

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, _check())
                    return future.result(timeout=10)
            else:
                return loop.run_until_complete(_check())
        except Exception:
            return False

    async def query(self, prompt: str) -> str:
        """Send a prompt and return the full response string."""
        _log.debug("OpenAI-compat query: model=%r, prompt_len=%d", self._model, len(prompt))
        chunks: list[str] = []
        async for chunk in self.stream(prompt):
            chunks.append(chunk)
        return "".join(chunks)

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        """Yield response text chunks from the OpenAI-compatible streaming API."""
        _log.debug("OpenAI-compat stream start: model=%r, prompt_len=%d", self._model, len(prompt))
        self._last_usage = None
        client = self._get_client()
        stream = await client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            temperature=self._temperature,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                self._last_usage = TokenUsage(
                    prompt_tokens=getattr(usage, "prompt_tokens", None),
                    completion_tokens=getattr(usage, "completion_tokens", None),
                )

    def get_last_usage(self) -> TokenUsage | None:
        """Return token usage reported by the server for the last stream() call, if any."""
        return self._last_usage
