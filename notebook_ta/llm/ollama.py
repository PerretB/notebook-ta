"""Ollama LLM provider implementation using the ollama Python package."""

from __future__ import annotations

import subprocess
import time
from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import ollama

from notebook_ta.llm.base import LLMProvider, TokenUsage
from notebook_ta.logging import get_logger

if TYPE_CHECKING:
    from notebook_ta.config.models import LLMConfig

_log = get_logger("llm.ollama")

_SERVER_START_TIMEOUT = 15  # seconds to wait after launching `ollama serve`
_SERVER_POLL_INTERVAL = 0.5  # seconds between readiness polls


class OllamaProvider(LLMProvider):
    """LLM provider that communicates with a local Ollama server via the ollama package."""

    def __init__(self, base_url: str, model: str, timeout: int, temperature: float = 0.7) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._temperature = temperature
        self._last_usage: TokenUsage | None = None

    @classmethod
    def from_config(cls, config: LLMConfig) -> OllamaProvider:
        return cls(
            base_url=config.base_url,
            model=config.model,
            timeout=config.timeout,
            temperature=config.temperature,
        )

    def _is_localhost(self) -> bool:
        """Return True if the configured host points to localhost."""
        hostname = urlparse(self._base_url).hostname or ""
        return hostname in ("localhost", "127.0.0.1", "::1")

    def _try_start_server(self) -> bool:
        """Launch 'ollama serve' and poll until it responds or the timeout expires."""
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (FileNotFoundError, OSError):
            return False
        poll_client = ollama.Client(host=self._base_url, timeout=2)
        deadline = time.monotonic() + _SERVER_START_TIMEOUT
        while time.monotonic() < deadline:
            time.sleep(_SERVER_POLL_INTERVAL)
            try:
                poll_client.list()
                return True
            except Exception:
                continue
        return False

    def _list_models(self, client: ollama.Client) -> set[str]:
        """Return the model names reported by an Ollama client."""
        return {model.model for model in client.list().models if model.model is not None}

    def _pull_model(self, client: ollama.Client, on_progress: Callable[[str], None]) -> bool:
        """Pull the configured model and report progress status updates."""
        try:
            for progress in client.pull(self._model, stream=True):
                if progress.status:
                    on_progress(progress.status)
            return self._model in self._list_models(client)
        except Exception as exc:
            _log.warning("Failed to pull Ollama model %r: %s", self._model, exc)
            return False

    def _setup_local(self, on_status: Callable[[str, str | None], None]) -> bool:
        """Start local Ollama if needed and ensure the configured model is installed."""
        client = ollama.Client(host=self._base_url, timeout=5)
        on_status("checking_server", None)
        try:
            models = self._list_models(client)
        except Exception:
            on_status("starting_server", None)
            if not self._try_start_server():
                on_status("server_failed", None)
                return False
            try:
                models = self._list_models(client)
            except Exception:
                on_status("server_failed", None)
                return False

        on_status("checking_model", None)
        if self._model not in models:
            on_status("pulling_model", None)
            if not self._pull_model(
                client, lambda detail: on_status("pulling_model", detail)
            ):
                on_status("model_failed", None)
                return False
        on_status("ready", None)
        return True

    def is_available(self) -> bool:
        """Return True if the Ollama server responds and the configured model exists."""
        client = ollama.Client(host=self._base_url, timeout=5)
        try:
            return self._model in self._list_models(client)
        except Exception:
            _log.warning("Ollama server not reachable at %r", self._base_url)
            return False

    async def query(self, prompt: str) -> str:
        """Send a prompt and accumulate the full response."""
        _log.debug("Ollama query: model=%r, prompt_len=%d", self._model, len(prompt))
        chunks: list[str] = []
        async for chunk in self.stream(prompt):
            chunks.append(chunk)
        return "".join(chunks)

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        """Yield response text chunks from the Ollama streaming API."""
        _log.debug("Ollama stream start: model=%r, prompt_len=%d", self._model, len(prompt))
        self._last_usage = None
        client = ollama.AsyncClient(host=self._base_url, timeout=self._timeout)
        async for part in await client.generate(
            model=self._model,
            prompt=prompt,
            stream=True,
            options={"temperature": self._temperature},
        ):
            if part.response:
                yield part.response
            if getattr(part, "done", False):
                self._last_usage = TokenUsage(
                    prompt_tokens=getattr(part, "prompt_eval_count", None),
                    completion_tokens=getattr(part, "eval_count", None),
                )

    def get_last_usage(self) -> TokenUsage | None:
        """Return token usage reported by the Ollama server for the last stream() call."""
        return self._last_usage
