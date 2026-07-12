"""Tests for provider setup performed by notebook_ta.load()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from notebook_ta import _setup_local_ollama
from notebook_ta.llm.ollama import OllamaProvider


def test_setup_local_ollama_runs_for_local_provider() -> None:
    """Local Ollama providers should be prepared during package loading."""
    provider = OllamaProvider("http://localhost:11434", "llama3.2:3b", 30)
    initialization = MagicMock()
    with patch.object(provider, "_setup_local", return_value=True) as setup:
        _setup_local_ollama(provider, initialization)

    setup.assert_called_once_with(initialization.update_ollama)


def test_setup_local_ollama_skips_remote_provider() -> None:
    """Remote Ollama providers must not be started or modified by package loading."""
    provider = OllamaProvider("http://ollama.example:11434", "llama3.2:3b", 30)
    with patch.object(provider, "_setup_local") as setup:
        _setup_local_ollama(provider)

    setup.assert_not_called()
