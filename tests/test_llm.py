"""Tests for LLM providers (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from notebook_ta.config.models import LLMConfig
from notebook_ta.llm.base import create_provider
from notebook_ta.llm.ollama import OllamaProvider
from notebook_ta.llm.openai_compat import OpenAICompatProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ollama_config(**kwargs) -> LLMConfig:
    defaults = dict(
        provider="ollama",
        model="llama3.2:3b",
        base_url="http://localhost:11434",
        timeout=30,
    )
    defaults.update(kwargs)
    return LLMConfig(**defaults)


def make_openai_config(**kwargs) -> LLMConfig:
    defaults = dict(
        provider="openai_compat",
        model="llama3.2:3b",
        base_url="http://localhost:1234/v1",
        api_key_env="NOTEBOOK_TA_TEST_API_KEY",
        timeout=30,
    )
    defaults.update(kwargs)
    return LLMConfig(**defaults)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestCreateProvider:
    def test_ollama_provider_created(self) -> None:
        provider = create_provider(make_ollama_config())
        assert isinstance(provider, OllamaProvider)

    def test_openai_compat_provider_created(self) -> None:
        provider = create_provider(make_openai_config())
        assert isinstance(provider, OpenAICompatProvider)

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValidationError, match="provider"):
            make_ollama_config(provider="unknown_provider")


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------

class TestOllamaProvider:
    def _make_list_response(self, *model_names: str) -> MagicMock:
        """Build a mock ListResponse with the given model names."""
        models = []
        for name in model_names:
            m = MagicMock()
            m.model = name
            models.append(m)
        resp = MagicMock()
        resp.models = models
        return resp

    def test_is_available_true(self) -> None:
        mock_list = self._make_list_response("llama3.2:3b")
        with patch("notebook_ta.llm.ollama.ollama.Client") as mock_cls:
            mock_cls.return_value.list.return_value = mock_list
            provider = OllamaProvider("http://localhost:11434", "llama3.2:3b", 30)
            assert provider.is_available() is True

    def test_is_available_false_for_remote_host(self) -> None:
        with patch("notebook_ta.llm.ollama.ollama.Client") as mock_cls:
            mock_cls.return_value.list.side_effect = Exception("Connection refused")
            provider = OllamaProvider("http://remote-host:11434", "llama3.2:3b", 30)
            assert provider.is_available() is False

    def test_is_available_does_not_start_server_on_localhost(self) -> None:
        with patch("notebook_ta.llm.ollama.ollama.Client") as mock_cls:
            mock_cls.return_value.list.side_effect = Exception("Connection refused")
            with patch("notebook_ta.llm.ollama.subprocess.Popen") as mock_popen:
                provider = OllamaProvider("http://localhost:11434", "llama3.2:3b", 30)
                assert provider.is_available() is False
        mock_popen.assert_not_called()

    def test_is_available_false_when_model_is_missing(self) -> None:
        with patch("notebook_ta.llm.ollama.ollama.Client") as mock_cls:
            mock_cls.return_value.list.return_value = self._make_list_response()
            provider = OllamaProvider("http://localhost:11434", "llama3.2:3b", 30)
            assert provider.is_available() is False

    def test_setup_local_starts_server_and_pulls_missing_model(self) -> None:
        missing_model = self._make_list_response()
        installed_model = self._make_list_response("llama3.2:3b")
        mock_progress = MagicMock()
        mock_progress.status = "pulling manifest"
        with patch("notebook_ta.llm.ollama.ollama.Client") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.list.side_effect = [
                Exception("Connection refused"),
                missing_model,
                installed_model,
            ]
            mock_client.pull.return_value = iter([mock_progress])
            provider = OllamaProvider("http://localhost:11434", "llama3.2:3b", 30)
            statuses: list[tuple[str, str | None]] = []
            with patch.object(provider, "_try_start_server", return_value=True) as start:
                result = provider._setup_local(lambda state, detail: statuses.append((state, detail)))
        assert result is True
        start.assert_called_once_with()
        mock_client.pull.assert_called_once_with("llama3.2:3b", stream=True)
        assert statuses == [
            ("checking_server", None),
            ("starting_server", None),
            ("checking_model", None),
            ("pulling_model", None),
            ("pulling_model", "pulling manifest"),
            ("ready", None),
        ]

    def test_setup_local_reports_server_start_failure(self) -> None:
        with patch("notebook_ta.llm.ollama.ollama.Client") as mock_cls:
            mock_cls.return_value.list.side_effect = Exception("Connection refused")
            provider = OllamaProvider("http://localhost:11434", "llama3.2:3b", 30)
            statuses: list[tuple[str, str | None]] = []
            with patch.object(provider, "_try_start_server", return_value=False):
                result = provider._setup_local(lambda state, detail: statuses.append((state, detail)))
        assert result is False
        assert statuses[-1] == ("server_failed", None)

    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self) -> None:
        def make_part(text: str) -> MagicMock:
            p = MagicMock()
            p.response = text
            return p

        async def fake_stream() -> None:
            for p in [make_part("Hello"), make_part(" world"), make_part("")]:
                yield p

        with patch("notebook_ta.llm.ollama.ollama.AsyncClient") as mock_cls:
            mock_cls.return_value.generate = AsyncMock(return_value=fake_stream())
            provider = OllamaProvider("http://localhost:11434", "llama3.2:3b", 30)
            chunks = []
            async for chunk in provider.stream("test prompt"):
                chunks.append(chunk)
        assert chunks == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_query_returns_full_response(self) -> None:
        def make_part(text: str) -> MagicMock:
            p = MagicMock()
            p.response = text
            return p

        async def fake_stream() -> None:
            for p in [make_part("Full"), make_part(" answer")]:
                yield p

        with patch("notebook_ta.llm.ollama.ollama.AsyncClient") as mock_cls:
            mock_cls.return_value.generate = AsyncMock(return_value=fake_stream())
            provider = OllamaProvider("http://localhost:11434", "llama3.2:3b", 30)
            result = await provider.query("prompt")
        assert result == "Full answer"

    def test_get_last_usage_defaults_to_none(self) -> None:
        provider = OllamaProvider("http://localhost:11434", "llama3.2:3b", 30)
        assert provider.get_last_usage() is None

    @pytest.mark.asyncio
    async def test_stream_captures_usage_from_final_chunk(self) -> None:
        def make_part(text: str = "", done: bool = False, prompt_eval_count=None, eval_count=None) -> MagicMock:
            p = MagicMock()
            p.response = text
            p.done = done
            p.prompt_eval_count = prompt_eval_count
            p.eval_count = eval_count
            return p

        async def fake_stream() -> None:
            for p in [
                make_part("Hello"),
                make_part(" world"),
                make_part("", done=True, prompt_eval_count=15, eval_count=8),
            ]:
                yield p

        with patch("notebook_ta.llm.ollama.ollama.AsyncClient") as mock_cls:
            mock_cls.return_value.generate = AsyncMock(return_value=fake_stream())
            provider = OllamaProvider("http://localhost:11434", "llama3.2:3b", 30)
            chunks = [c async for c in provider.stream("prompt")]

        assert chunks == ["Hello", " world"]
        usage = provider.get_last_usage()
        assert usage is not None
        assert usage.prompt_tokens == 15
        assert usage.completion_tokens == 8


# ---------------------------------------------------------------------------
# OpenAICompatProvider — is_available
# ---------------------------------------------------------------------------

class TestOpenAICompatProvider:
    def test_from_config(self) -> None:
        cfg = make_openai_config()
        provider = OpenAICompatProvider.from_config(cfg)
        assert isinstance(provider, OpenAICompatProvider)

    def test_get_last_usage_defaults_to_none(self) -> None:
        provider = OpenAICompatProvider.from_config(make_openai_config())
        assert provider.get_last_usage() is None

    @pytest.mark.asyncio
    async def test_stream_captures_usage_from_final_chunk(self) -> None:
        def make_chunk(content: str | None = None, usage=None) -> MagicMock:
            chunk = MagicMock()
            if content is not None:
                choice = MagicMock()
                choice.delta.content = content
                chunk.choices = [choice]
            else:
                chunk.choices = []
            chunk.usage = usage
            return chunk

        usage_obj = MagicMock(prompt_tokens=12, completion_tokens=7)

        async def fake_stream() -> None:
            for c in [make_chunk(content="Hello"), make_chunk(content=" world"), make_chunk(usage=usage_obj)]:
                yield c

        provider = OpenAICompatProvider.from_config(make_openai_config())
        with patch.object(provider, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=fake_stream())
            mock_get_client.return_value = mock_client
            chunks = [c async for c in provider.stream("prompt")]

        assert chunks == ["Hello", " world"]
        usage = provider.get_last_usage()
        assert usage is not None
        assert usage.prompt_tokens == 12
        assert usage.completion_tokens == 7
