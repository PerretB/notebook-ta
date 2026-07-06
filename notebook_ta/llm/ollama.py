"""Ollama LLM provider implementation using the ollama Python package."""

from __future__ import annotations

import subprocess
import time
from typing import TYPE_CHECKING, AsyncIterator
from urllib.parse import urlparse

import ollama

from notebook_ta.llm.base import LLMProvider, TokenUsage
from notebook_ta.logging import get_logger

if TYPE_CHECKING:
    from notebook_ta.config.models import LLMConfig

_log = get_logger("llm.ollama")

_SERVER_START_TIMEOUT = 15  # seconds to wait after launching `ollama serve`
_SERVER_POLL_INTERVAL = 1  # seconds between readiness polls


class OllamaProvider(LLMProvider):
    """LLM provider that communicates with a local Ollama server via the ollama package."""

    def __init__(self, base_url: str, model: str, timeout: int, temperature: float = 0.7) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._temperature = temperature
        self._last_usage: TokenUsage | None = None

    @classmethod
    def from_config(cls, config: "LLMConfig") -> "OllamaProvider":
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

    def _ensure_model(self, client: ollama.Client) -> None:
        """Pull the configured model if it is not already present locally."""
        try:
            available = {m.model for m in client.list().models}
            if self._model not in available:
                print(f"[notebook-ta] Model '{self._model}' not found — pulling…")
                for progress in client.pull(self._model, stream=True):
                    if progress.status:
                        print(f"\r[notebook-ta] {progress.status}", end="", flush=True)
                print()  # newline after last progress line
        except Exception:
            pass  # best-effort; generation will fail gracefully if the model is missing

    def is_available(self) -> bool:
        """Return True if the Ollama server is ready and the model is available.

        For localhost deployments, attempts to start the server when it is not
        running and pulls the configured model if it has not been downloaded yet.
        """
        client = ollama.Client(host=self._base_url, timeout=5)
        try:
            client.list()
        except Exception:
            if not self._is_localhost():
                _log.warning("Ollama server not reachable at %r", self._base_url)
                return False
            print("[notebook-ta] Ollama server not running — starting…")
            if not self._try_start_server():
                _log.warning("Failed to start Ollama server at %r", self._base_url)
                return False
        self._ensure_model(client)
        return True

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
