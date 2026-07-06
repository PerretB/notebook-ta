"""Tests for the %%notebook_ta cell magic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from notebook_ta.config.models import ExerciseConfig, GlobalConfig, LLMConfig, PromptConfig
from notebook_ta.exercise.definition import Exercise
from notebook_ta.exercise.registry import ExerciseRegistry
from notebook_ta.notebook.magic import NotebookTAMagic, load_ipython_extension
from notebook_ta.notebook.session import SessionState
from notebook_ta.testing.runner import TestResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_global_config() -> GlobalConfig:
    return GlobalConfig(
        llm=LLMConfig(provider="ollama", model="llama3.2:3b", base_url="http://localhost:11434"),
        prompts=PromptConfig(
            on_success="Good job.",
            on_failure="Try again.",
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


def make_magic(
    ip: MagicMock | None = None,
    exercises: list[Exercise] | None = None,
    llm_available: bool = True,
) -> NotebookTAMagic:
    if ip is None:
        ip = make_ip_stub()
    registry = ExerciseRegistry()
    for ex in exercises or [make_exercise()]:
        registry.register(ex)
    llm = MagicMock()
    llm.is_available.return_value = llm_available
    # stream returns an async generator yielding "Good feedback"
    async def _stream(prompt: str):
        yield "Good feedback"
    llm.stream = _stream
    session = SessionState(hint_history_length=3)
    # Pass None as shell to satisfy traitlets, then set the stub after construction
    magic = NotebookTAMagic(shell=None, registry=registry, llm_provider=llm, session=session)
    magic.shell = ip
    return magic


# ---------------------------------------------------------------------------
# Magic registration
# ---------------------------------------------------------------------------

class TestMagicRegistration:
    def test_load_ipython_extension_registers_magic(self) -> None:
        ip = MagicMock()
        registry = ExerciseRegistry()
        llm = MagicMock()
        session = SessionState()
        with patch("notebook_ta.notebook.magic.NotebookTAMagic") as MockMagic:
            load_ipython_extension(ip, registry=registry, llm_provider=llm, session=session)
        ip.register_magics.assert_called_once_with(MockMagic.return_value)


# ---------------------------------------------------------------------------
# Cell magic — tests pass
# ---------------------------------------------------------------------------

class TestCellMagicAllPass:
    @patch("notebook_ta.notebook.magic.display")
    @patch("notebook_ta.notebook.magic.stream_to_output")
    def test_display_success_called(self, mock_stream, mock_display) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip)

        # Patch runner to return all-pass
        with patch.object(magic._runner, "run", return_value=[TestResult("t", True)]):
            with patch("asyncio.get_event_loop") as mock_loop:
                loop = MagicMock()
                loop.run_until_complete = MagicMock(return_value="feedback")
                mock_loop.return_value = loop
                magic.notebook_ta("ex1", "def add(a,b): return a+b")

        mock_display.display_success.assert_called_once()

    @patch("notebook_ta.notebook.magic.display")
    def test_student_code_executed_in_namespace(self, mock_display) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip)

        with patch.object(magic._runner, "run", return_value=[TestResult("t", True)]):
            with patch("asyncio.get_event_loop") as mock_loop:
                loop = MagicMock()
                loop.run_until_complete = MagicMock(return_value="feedback")
                mock_loop.return_value = loop
                magic.notebook_ta("ex1", "x = 42")

        ip.run_cell.assert_called_once_with("x = 42")


# ---------------------------------------------------------------------------
# Cell magic — tests fail
# ---------------------------------------------------------------------------

class TestCellMagicSomeFail:
    @patch("notebook_ta.notebook.magic.display")
    def test_display_test_results_and_button_called(self, mock_display) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip)
        failing_results = [TestResult("t", False, "Wrong")]

        with patch.object(magic._runner, "run", return_value=failing_results):
            magic.notebook_ta("ex1", "def add(a,b): return 0")

        mock_display.display_test_results.assert_called_once_with(failing_results)
        mock_display.display_hints_button.assert_called_once()


# ---------------------------------------------------------------------------
# Cell magic — unknown exercise ID
# ---------------------------------------------------------------------------

class TestUnknownExercise:
    @patch("notebook_ta.notebook.magic.display")
    def test_display_unavailable_when_id_not_found(self, mock_display) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip)
        magic.notebook_ta("UNKNOWN_ID", "code")
        mock_display.display_unavailable_message.assert_called_once_with("UNKNOWN_ID")


# ---------------------------------------------------------------------------
# Cell magic — LLM unavailable
# ---------------------------------------------------------------------------

class TestLLMUnavailable:
    @patch("notebook_ta.notebook.magic.display")
    def test_no_llm_message_when_unavailable(self, mock_display) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip, llm_available=False)

        with patch.object(magic._runner, "run", return_value=[TestResult("t", True)]):
            magic.notebook_ta("ex1", "def add(a,b): return a+b")

        mock_display.display_no_llm_message.assert_called_once()


# ---------------------------------------------------------------------------
# Hint history accumulation
# ---------------------------------------------------------------------------

class TestHintHistory:
    def test_hint_appended_to_session(self) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip)
        failing_results = [TestResult("t", False)]

        async def _fake_stream(prompt):
            yield "Hint response"

        magic._llm.stream = _fake_stream

        with patch("asyncio.get_event_loop") as mock_loop:
            loop = MagicMock()
            loop.run_until_complete = MagicMock(return_value="Hint response")
            mock_loop.return_value = loop
            magic._hint_callback("ex1", "student code", failing_results)

        history = magic._session.get_history("ex1", 3)
        assert len(history) == 1
        assert history[0].student_code == "student code"
        assert history[0].hint_response == "Hint response"

    def test_hint_deque_truncates_at_limit(self) -> None:
        session = SessionState(hint_history_length=2)
        from notebook_ta.notebook.session import HintExchange

        for i in range(4):
            session.append_hint("ex1", HintExchange(f"code{i}", f"hint{i}"))

        history = session.get_history("ex1", 2)
        assert len(history) == 2
        assert history[-1].hint_response == "hint3"
        assert history[0].hint_response == "hint2"


# ---------------------------------------------------------------------------
# Debug mode — prompt display
# ---------------------------------------------------------------------------


class TestDebugMode:
    def _make_debug_magic(self, ip: MagicMock | None = None) -> NotebookTAMagic:
        if ip is None:
            ip = make_ip_stub()
        registry = ExerciseRegistry()
        registry.register(make_exercise())
        llm = MagicMock()
        llm.is_available.return_value = True

        async def _stream(prompt: str):
            yield "Good feedback"

        llm.stream = _stream
        session = SessionState(hint_history_length=3)
        magic = NotebookTAMagic(
            shell=None,
            registry=registry,
            llm_provider=llm,
            session=session,
            debug=True,
        )
        magic.shell = ip
        return magic

    @patch("notebook_ta.notebook.magic.display")
    def test_debug_prompt_displayed_on_analysis(self, mock_display) -> None:
        ip = make_ip_stub()
        magic = self._make_debug_magic(ip=ip)

        with patch.object(magic._runner, "run", return_value=[TestResult("t", True)]):
            with patch("asyncio.get_event_loop") as mock_loop:
                loop = MagicMock()
                loop.run_until_complete = MagicMock(return_value="feedback")
                mock_loop.return_value = loop
                magic.notebook_ta("ex1", "def add(a,b): return a+b")

        mock_display.display_debug_prompt.assert_called_once()
        call_kwargs = mock_display.display_debug_prompt.call_args
        assert call_kwargs.kwargs.get("call_type") == "analysis" or (
            len(call_kwargs.args) >= 2 and call_kwargs.args[1] == "analysis"
        )

    @patch("notebook_ta.notebook.magic.display")
    def test_debug_prompt_not_displayed_when_debug_false(self, mock_display) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip)  # debug defaults to False

        with patch.object(magic._runner, "run", return_value=[TestResult("t", True)]):
            with patch("asyncio.get_event_loop") as mock_loop:
                loop = MagicMock()
                loop.run_until_complete = MagicMock(return_value="feedback")
                mock_loop.return_value = loop
                magic.notebook_ta("ex1", "def add(a,b): return a+b")

        mock_display.display_debug_prompt.assert_not_called()

    @patch("notebook_ta.notebook.magic.display")
    def test_debug_prompt_displayed_on_hint(self, mock_display) -> None:
        ip = make_ip_stub()
        magic = self._make_debug_magic(ip=ip)
        failing_results = [TestResult("t", False)]

        with patch("asyncio.get_event_loop") as mock_loop:
            loop = MagicMock()
            loop.run_until_complete = MagicMock(return_value="Hint response")
            mock_loop.return_value = loop
            magic._hint_callback("ex1", "student code", failing_results)

        mock_display.display_debug_prompt.assert_called_once()
        call_kwargs = mock_display.display_debug_prompt.call_args
        assert call_kwargs.kwargs.get("call_type") == "hint" or (
            len(call_kwargs.args) >= 2 and call_kwargs.args[1] == "hint"
        )
