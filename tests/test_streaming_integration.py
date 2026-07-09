"""Integration test for streaming output — verify no duplication."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

from IPython import display as ipydisplay

from notebook_ta.config.models import ExerciseConfig, GlobalConfig, LLMConfig, PromptConfig
from notebook_ta.exercise.definition import Exercise
from notebook_ta.exercise.registry import ExerciseRegistry
from notebook_ta.notebook.magic import NotebookTAMagic
from notebook_ta.notebook.session import SessionState
from notebook_ta.testing.runner import TestResult


def run_mocked_coroutine(result: str):
    """Return a run_until_complete mock that closes the coroutine passed by production code."""

    def _run(coro):
        coro.close()
        return result

    return MagicMock(side_effect=_run)


class FakeLLMProvider:
    """Fake LLM provider that yields known chunks in a stream."""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    def is_available(self) -> bool:
        return True

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        """Yield predefined chunks."""
        for chunk in self._chunks:
            yield chunk

    async def query(self, prompt: str) -> str:
        """Return concatenated chunks."""
        return "".join(self._chunks)


def make_global_config() -> GlobalConfig:
    return GlobalConfig(
        llm=LLMConfig(provider="ollama", model="test", base_url="http://localhost:11434"),
        prompts=PromptConfig(
            on_success="Good job.",
            on_failure="Try again.",
            on_hints="Here is a hint.",
            on_no_llm="LLM unavailable.",
            hint_history_length=3,
        ),
    )


def make_exercise(exercise_id: str = "ex1") -> Exercise:
    cfg = ExerciseConfig(
        id=exercise_id,
        statement="Write an add function.",
    )
    return Exercise(config=cfg, global_config=make_global_config())


def make_ip_stub(user_ns: dict | None = None) -> MagicMock:
    """Create a minimal IPython stub."""
    ip = MagicMock()
    ip.user_ns = user_ns or {"add": lambda a, b: a + b}
    ip.run_cell = MagicMock()
    return ip


class TestStreamingIntegration:
    """Verify that streamed output appears exactly once, not duplicated."""

    @patch("notebook_ta.notebook.magic.display")
    def test_streamed_output_not_duplicated(self, mock_display: MagicMock) -> None:
        """
        Run the %%notebook_ta magic with a fake LLM that streams in chunks.
        Verify that stream_to_output handles the chunks without duplication.
        """
        # Set up exercise and magic
        ip = make_ip_stub()
        registry = ExerciseRegistry()
        registry.register(make_exercise("ex1"))

        # Fake LLM that streams 3 chunks
        llm = FakeLLMProvider(chunks=["This ", "is ", "feedback."])

        session = SessionState(hint_history_length=3)
        magic = NotebookTAMagic(
            shell=None,
            registry=registry,
            llm_provider=llm,
            session=session,
        )
        magic.shell = ip

        # Mock runner to return all-pass, which triggers LLM feedback
        with (
            patch.object(magic._runner, "run", return_value=[TestResult("test", True)]),
            patch("asyncio.get_event_loop") as mock_loop,
        ):
            loop = MagicMock()
            loop.run_until_complete = run_mocked_coroutine("This is feedback.")
            mock_loop.return_value = loop
            magic.notebook_ta("ex1", "def add(a, b): return a + b")

        # Verify display_success was called (initial "all tests passed" message)
        mock_display.display_success.assert_called_once()

    @patch("IPython.display.display")
    def test_stream_to_output_uses_display_id(
        self, mock_ipydisplay: MagicMock
    ) -> None:
        """
        Verify that stream_to_output() calls display with display_id=True
        and update() is called on each chunk (not creating new displays).
        """
        from notebook_ta.notebook.streaming import stream_to_output

        # Mock display handle
        mock_handle = MagicMock()
        mock_ipydisplay.return_value = mock_handle

        # Async generator that yields 3 chunks
        async def fake_stream() -> AsyncIterator[str]:
            for chunk in ["Hello ", "world", "!"]:
                yield chunk

        # Run stream_to_output with a proper event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(stream_to_output(fake_stream()))
        finally:
            loop.close()

        # Verify result is the concatenation
        assert result == "Hello world!"

        # Verify display() was called exactly once with display_id=True
        mock_ipydisplay.assert_called_once()
        call_kwargs = mock_ipydisplay.call_args[1]
        assert call_kwargs.get("display_id") is True

        # Verify update() was called 3 times (once per chunk)
        assert mock_handle.update.call_count == 3
        first_display = mock_ipydisplay.call_args.args[0]
        assert isinstance(first_display, ipydisplay.Markdown)
        assert "background: rgba(20, 184, 166, 0.14)" in first_display.data

        final_update = mock_handle.update.call_args.args[0]
        assert isinstance(final_update, ipydisplay.Markdown)
        assert "🤖 Hello world!" in final_update.data

        # Verify no duplicate displays
        assert mock_ipydisplay.call_count == 1
