"""Tests for the %%notebook_ta cell magic."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from IPython.core.interactiveshell import InteractiveShell

from notebook_ta.config.models import ExerciseConfig, GlobalConfig, LLMConfig, PromptConfig
from notebook_ta.exercise.definition import Exercise
from notebook_ta.exercise.registry import ExerciseRegistry
from notebook_ta.llm.postprocessing import AnswerPostprocessor, LLMRequest
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


def make_free_text_exercise(exercise_id: str = "explain") -> Exercise:
    """Create a free-text exercise with an exercise-level evaluation prompt."""
    cfg = ExerciseConfig(
        id=exercise_id,
        answer_type="free_text",
        statement="Explain recursion.",
        prompt_on_free_text="Evaluate this explanation.",
    )
    return Exercise(config=cfg, global_config=make_global_config())


def make_ip_stub(user_ns: dict | None = None) -> MagicMock:
    """Create a minimal IPython stub."""
    ip = MagicMock()
    ip.user_ns = user_ns or {"add": lambda a, b: a + b}
    ip.run_cell = MagicMock(
        return_value=SimpleNamespace(error_before_exec=None, error_in_exec=None)
    )
    return ip


def make_magic(
    ip: MagicMock | None = None,
    exercises: list[Exercise] | None = None,
    llm_available: bool = True,
    answer_postprocessor: AnswerPostprocessor | None = None,
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
    magic = NotebookTAMagic(
        shell=None,
        registry=registry,
        llm_provider=llm,
        session=session,
        answer_postprocessor=answer_postprocessor,
    )
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
        with (
            patch("notebook_ta.notebook.magic.NotebookTAMagic") as MockMagic,
            patch("notebook_ta.notebook.magic._active_magic_instance", None),
        ):
            load_ipython_extension(ip, registry=registry, llm_provider=llm, session=session)
        ip.register_magics.assert_called_once_with(MockMagic.return_value)

    def test_reload_shuts_down_previously_registered_magic(self) -> None:
        """Rerunning a setup cell must not leave the previous dispatcher alive."""
        ip = MagicMock()
        registry = ExerciseRegistry()
        llm = MagicMock()
        session = SessionState()
        first_magic = MagicMock()
        second_magic = MagicMock()

        with (
            patch(
                "notebook_ta.notebook.magic.NotebookTAMagic",
                side_effect=[first_magic, second_magic],
            ),
            patch("notebook_ta.notebook.magic._active_magic_instance", None),
        ):
            load_ipython_extension(ip, registry=registry, llm_provider=llm, session=session)
            load_ipython_extension(ip, registry=registry, llm_provider=llm, session=session)

        first_magic.shutdown_now.assert_called_once_with()
        second_magic.shutdown_now.assert_not_called()
        assert ip.register_magics.call_args_list == [
            call(first_magic),
            call(second_magic),
        ]


# ---------------------------------------------------------------------------
# Cell magic — tests pass
# ---------------------------------------------------------------------------

class TestCellMagicAllPass:
    @patch("notebook_ta.notebook.magic.display")
    def test_repeated_execution_explicitly_clears_previous_cell_output(
        self,
        mock_display: MagicMock,
    ) -> None:
        """Every invocation clears saved results instead of relying on frontend behavior."""
        ip = make_ip_stub()
        magic = make_magic(ip=ip, llm_available=False)

        with patch.object(
            magic._runner,
            "run",
            return_value=[TestResult("t", True)],
        ):
            magic.notebook_ta("ex1", "answer = 1")
            magic.notebook_ta("ex1", "answer = 2")

        assert mock_display.clear_cell_output.call_count == 2
        assert ip.run_cell.call_count == 2

    @patch("notebook_ta.notebook.magic._log")
    @patch("notebook_ta.notebook.magic.display")
    def test_oversized_answer_runs_tests_but_skips_llm(
        self, mock_display, mock_log
    ) -> None:
        ip = make_ip_stub()
        global_config = make_global_config()
        global_config.max_student_answer_length = 5
        exercise = Exercise(
            ExerciseConfig(id="ex1", statement="Write an add function."),
            global_config,
        )
        magic = make_magic(ip=ip, exercises=[exercise])
        results = [TestResult("t", True)]

        with patch.object(magic._runner, "run", return_value=results) as run_tests:
            magic.notebook_ta("ex1", "answer")

        ip.run_cell.assert_called_once_with("answer")
        run_tests.assert_called_once()
        mock_display.display_test_results.assert_called_once_with(results)
        mock_display.display_success.assert_not_called()
        mock_display.display_hints_button.assert_not_called()
        magic._llm.is_available.assert_not_called()
        mock_log.error.assert_called_once()

    @patch("notebook_ta.notebook.magic.display")
    @patch("notebook_ta.notebook.magic.stream_to_output", new_callable=AsyncMock)
    def test_display_success_called(self, mock_stream, mock_display) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip)
        mock_stream.return_value = "feedback"
        loop = asyncio.new_event_loop()

        # Patch runner to return all-pass
        try:
            with (
                patch.object(magic._runner, "run", return_value=[TestResult("t", True)]),
                patch("asyncio.get_event_loop", return_value=loop),
            ):
                magic.notebook_ta("ex1", "def add(a,b): return a+b")
        finally:
            loop.close()

        mock_display.display_success.assert_called_once()

    @patch("notebook_ta.notebook.magic.display")
    def test_student_code_executed_in_namespace(self, mock_display) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip, llm_available=False)
        loop = asyncio.new_event_loop()

        try:
            with (
                patch.object(magic._runner, "run", return_value=[TestResult("t", True)]),
                patch("asyncio.get_event_loop", return_value=loop),
            ):
                magic.notebook_ta("ex1", "x = 42")
        finally:
            loop.close()

        ip.run_cell.assert_called_once_with("x = 42")


class TestFreeTextCellMagic:
    @patch("notebook_ta.notebook.magic.display")
    def test_submission_skips_python_and_tests_and_triggers_llm(self, mock_display) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip, exercises=[make_free_text_exercise()])

        with (
            patch.object(magic._runner, "run") as run_tests,
            patch.object(magic, "_trigger_llm", return_value=None) as trigger_llm,
        ):
            magic.notebook_ta("explain", "Recursion calls a function itself.")

        ip.run_cell.assert_not_called()
        run_tests.assert_not_called()
        trigger_llm.assert_called_once_with(
            "explain",
            "Recursion calls a function itself.",
            results=None,
            hint_history=None,
        )
        mock_display.display_success.assert_not_called()
        mock_display.display_test_results.assert_not_called()
        mock_display.display_hints_button.assert_not_called()

    @patch("notebook_ta.notebook.magic._log")
    @patch("notebook_ta.notebook.magic.display")
    def test_empty_submission_is_rejected(self, mock_display, mock_log) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip, exercises=[make_free_text_exercise()])

        with patch.object(magic, "_trigger_llm") as trigger_llm:
            magic.notebook_ta("explain", "  \n")

        ip.run_cell.assert_not_called()
        trigger_llm.assert_not_called()
        mock_log.error.assert_called_once_with("The student answer cannot be empty.")
        mock_display.display_success.assert_not_called()

    @patch("notebook_ta.notebook.magic._log")
    def test_oversized_submission_is_rejected_before_llm(self, mock_log) -> None:
        ip = make_ip_stub()
        exercise = make_free_text_exercise()
        exercise.config.max_student_answer_length = 5
        magic = make_magic(ip=ip, exercises=[exercise])

        magic.notebook_ta("explain", "too long")

        ip.run_cell.assert_not_called()
        magic._llm.is_available.assert_not_called()
        assert "No request was sent to the LLM" in mock_log.error.call_args.args[0]


# ---------------------------------------------------------------------------
# Cell magic — tests fail
# ---------------------------------------------------------------------------

class TestCellMagicSomeFail:
    @patch("notebook_ta.notebook.magic.display")
    def test_display_test_results_and_button_called(self, mock_display) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip)
        failing_results = [TestResult("t", False, "Wrong")]
        loop = asyncio.new_event_loop()

        try:
            with (
                patch.object(magic._runner, "run", return_value=failing_results),
                patch("asyncio.get_event_loop", return_value=loop),
            ):
                magic.notebook_ta("ex1", "def add(a,b): return 0")
        finally:
            loop.close()

        mock_display.display_test_results.assert_called_once_with(failing_results)
        mock_display.display_hints_button.assert_called_once()


# ---------------------------------------------------------------------------
# Cell magic — student-code execution fails
# ---------------------------------------------------------------------------

class TestCellExecutionFailure:
    @patch("notebook_ta.notebook.magic.display")
    def test_syntax_error_stops_tests_and_llm_with_stale_symbol_present(
        self, mock_display
    ) -> None:
        shell = InteractiveShell()
        shell.run_cell("def add(a, b):\n    return a + b")
        stale_add = shell.user_ns["add"]
        magic = make_magic(ip=cast(MagicMock, shell))

        with patch.object(magic._runner, "run") as run_tests:
            magic.notebook_ta("ex1", "def add(a, b)\n    return a - b")

        assert shell.user_ns["add"] is stale_add
        run_tests.assert_not_called()
        magic._llm.is_available.assert_not_called()
        error = mock_display.display_execution_failure.call_args.args[0]
        assert isinstance(error, SyntaxError)

    @patch("notebook_ta.notebook.magic.display")
    def test_runtime_error_stops_tests_and_llm_with_stale_symbol_present(
        self, mock_display
    ) -> None:
        shell = InteractiveShell()
        shell.run_cell("def add(a, b):\n    return a + b")
        stale_add = shell.user_ns["add"]
        magic = make_magic(ip=cast(MagicMock, shell))

        with patch.object(magic._runner, "run") as run_tests:
            magic.notebook_ta("ex1", "raise RuntimeError('broken submission')")

        assert shell.user_ns["add"] is stale_add
        run_tests.assert_not_called()
        magic._llm.is_available.assert_not_called()
        error = mock_display.display_execution_failure.call_args.args[0]
        assert isinstance(error, RuntimeError)


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
        ip.run_cell.assert_not_called()


# ---------------------------------------------------------------------------
# Cell magic — LLM unavailable
# ---------------------------------------------------------------------------

class TestLLMUnavailable:
    @patch("notebook_ta.notebook.magic.display")
    def test_no_llm_message_when_unavailable(self, mock_display) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip, llm_available=False)
        loop = asyncio.new_event_loop()

        try:
            with (
                patch.object(magic._runner, "run", return_value=[TestResult("t", True)]),
                patch("asyncio.get_event_loop", return_value=loop),
            ):
                magic.notebook_ta("ex1", "def add(a,b): return a+b")
        finally:
            loop.close()

        mock_display.display_no_llm_message.assert_called_once()

    @patch("notebook_ta.notebook.magic.stream_to_output", new_callable=AsyncMock)
    @patch("notebook_ta.notebook.magic.display")
    def test_no_llm_message_when_analysis_stream_fails(
        self, mock_display, mock_stream
    ) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip, llm_available=True)
        mock_stream.side_effect = RuntimeError("stream dropped")
        loop = asyncio.new_event_loop()

        try:
            with (
                patch.object(magic._runner, "run", return_value=[TestResult("t", True)]),
                patch("asyncio.get_event_loop", return_value=loop),
            ):
                magic.notebook_ta("ex1", "def add(a,b): return a+b")
        finally:
            loop.close()

        mock_display.LLMOutput.return_value.show_unavailable.assert_called_once_with(
            "LLM unavailable."
        )

    @patch("notebook_ta.notebook.magic.stream_to_output", new_callable=AsyncMock)
    @patch("notebook_ta.notebook.magic.display")
    def test_failed_hint_stream_is_not_saved_to_history(
        self, mock_display, mock_stream
    ) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip, llm_available=True)
        mock_stream.side_effect = RuntimeError("stream dropped")
        loop = asyncio.new_event_loop()

        try:
            with patch("asyncio.get_event_loop", return_value=loop):
                magic._hint_callback("ex1", "student code", [TestResult("t", False)])
        finally:
            loop.close()

        mock_display.LLMOutput.return_value.show_unavailable.assert_called_once_with(
            "LLM unavailable."
        )
        assert magic._session.get_history("ex1", 3) == []


# ---------------------------------------------------------------------------
# Serial LLM queue
# ---------------------------------------------------------------------------


class TestSerialLLMQueue:
    @patch("notebook_ta.notebook.magic.display")
    async def test_run_all_runs_each_test_suite_before_serial_analysis(
        self,
        mock_display: MagicMock,
    ) -> None:
        """Later notebook cells run and test while the first LLM stream is active."""
        ip = make_ip_stub()
        magic = make_magic(
            ip=ip,
            exercises=[make_exercise("ex1"), make_exercise("ex2")],
        )
        first_stream_started = asyncio.Event()
        release_first_stream = asyncio.Event()
        started_prompts: list[str] = []

        async def _stream(prompt: str):
            started_prompts.append(prompt)
            if len(started_prompts) == 1:
                first_stream_started.set()
                await release_first_stream.wait()
            yield "feedback"

        magic._llm.stream = _stream
        passing_results = [TestResult("t", True)]

        with patch.object(magic._runner, "run", return_value=passing_results) as run_tests:
            magic.notebook_ta("ex1", "first_answer = 1")
            await first_stream_started.wait()

            magic.notebook_ta("ex2", "second_answer = 2")

            assert ip.run_cell.call_count == 2
            assert run_tests.call_count == 2
            assert len(started_prompts) == 1
            assert mock_display.LLMOutput.call_count == 2

            release_first_stream.set()
            worker = magic._dispatcher._worker_task
            assert worker is not None
            await worker

        assert len(started_prompts) == 2
        mock_display.display_busy_message.assert_not_called()


class TestLLMCancellation:
    @patch("notebook_ta.notebook.magic.display")
    async def test_cancelled_hint_is_not_saved_to_history(
        self,
        mock_display: MagicMock,
    ) -> None:
        """Cancelling a queued hint must not record a partial exchange."""
        magic = make_magic()
        stream_started = asyncio.Event()

        async def _stream_to_output(_stream: object, **_kwargs: object) -> str:
            stream_started.set()
            await asyncio.Event().wait()
            return "unreachable"

        with patch(
            "notebook_ta.notebook.magic.stream_to_output",
            side_effect=_stream_to_output,
        ):
            result = magic._hint_callback(
                "ex1",
                "student code",
                [TestResult("fails", False)],
            )
            assert isinstance(result, asyncio.Future)
            await stream_started.wait()

            assert magic._dispatcher.cancel_all() == 1
            with pytest.raises(asyncio.CancelledError):
                await result

        assert magic._session.get_history("ex1", 3) == []
        mock_display.LLMOutput.return_value.show_cancelled.assert_called_once_with()

    @patch("notebook_ta.notebook.magic.display")
    def test_interrupted_tests_do_not_enqueue_analysis(self, mock_display: MagicMock) -> None:
        """A foreground interruption must propagate before any background job exists."""
        magic = make_magic()

        with (
            patch.object(magic._runner, "run", side_effect=KeyboardInterrupt),
            patch.object(magic, "_trigger_llm") as trigger_llm,
            pytest.raises(KeyboardInterrupt),
        ):
            magic.notebook_ta("ex1", "answer = 1")

        trigger_llm.assert_not_called()
        assert magic._dispatcher.pending_count == 0
        assert magic._dispatcher.is_active is False
        mock_display.LLMOutput.assert_not_called()


# ---------------------------------------------------------------------------
# Hint history accumulation
# ---------------------------------------------------------------------------

class TestHintHistory:
    @patch("notebook_ta.notebook.magic.display")
    def test_cell_execution_does_not_toggle_all_hint_buttons(self, mock_display) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip)
        failing_results = [TestResult("t", False)]

        with patch.object(magic._runner, "run", return_value=failing_results):
            magic.notebook_ta("ex1", "def add(a,b): return 0")

        ip.run_cell.assert_called_once_with("def add(a,b): return 0")
        mock_display.display_test_results.assert_called_once_with(failing_results)
        mock_display.set_hint_buttons_busy.assert_not_called()

    @patch("notebook_ta.notebook.magic.display")
    def test_test_exception_does_not_toggle_all_hint_buttons(self, mock_display) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip)

        with patch.object(magic._runner, "run", side_effect=RuntimeError("boom")):
            try:
                magic.notebook_ta("ex1", "def add(a,b): return 0")
            except RuntimeError as exc:
                assert str(exc) == "boom"

        mock_display.set_hint_buttons_busy.assert_not_called()

    def test_hint_appended_to_session(self) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip)
        failing_results = [TestResult("t", False)]
        loop = asyncio.new_event_loop()

        async def _fake_stream(prompt):
            yield "Hint response"

        magic._llm.stream = _fake_stream

        try:
            with (
                patch("asyncio.get_event_loop", return_value=loop),
                patch(
                    "notebook_ta.notebook.magic.stream_to_output",
                    new_callable=AsyncMock,
                ) as mock_stream,
            ):
                mock_stream.return_value = "Hint response"
                magic._hint_callback("ex1", "student code", failing_results)
        finally:
            loop.close()

        history = magic._session.get_history("ex1", 3)
        assert len(history) == 1
        assert history[0].student_code == "student code"
        assert history[0].hint_response == "Hint response"

    async def test_async_hint_task_is_retained_until_completion(self) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip)
        failing_results = [TestResult("t", False)]
        stream_started = asyncio.Event()
        release_stream = asyncio.Event()

        async def _stream_to_output(_stream: object, **_kwargs: object) -> str:
            stream_started.set()
            await release_stream.wait()
            return "Hint response"

        with patch("notebook_ta.notebook.magic.stream_to_output", side_effect=_stream_to_output):
            result = magic._hint_callback("ex1", "student code", failing_results)
            assert isinstance(result, Awaitable)

            await stream_started.wait()
            future = cast(asyncio.Future[bool | None], result)
            assert magic._dispatcher.is_active is True

            release_stream.set()
            assert await future is True

        assert magic._dispatcher.is_active is False

    @patch("notebook_ta.notebook.magic.display")
    async def test_running_hint_queues_overlapping_cell_and_hint_requests(
        self,
        mock_display: MagicMock,
    ) -> None:
        """An active hint must not prevent later cells from running tests and queueing work."""
        ip = make_ip_stub()
        magic = make_magic(ip=ip)
        failing_results = [TestResult("t", False)]
        stream_started = asyncio.Event()
        release_stream = asyncio.Event()

        stream_calls = 0

        async def _stream_to_output(_stream: object, **_kwargs: object) -> str:
            nonlocal stream_calls
            stream_calls += 1
            if stream_calls == 1:
                stream_started.set()
                await release_stream.wait()
            return f"Hint response {stream_calls}"

        with patch(
            "notebook_ta.notebook.magic.stream_to_output",
            side_effect=_stream_to_output,
        ) as mock_stream:
            first_hint = magic._hint_callback("ex1", "student code", failing_results)
            assert isinstance(first_hint, Awaitable)
            await stream_started.wait()

            with patch.object(magic._runner, "run", return_value=failing_results) as run_tests:
                magic.notebook_ta("ex1", "def add(a,b): return 0")
            second_hint = magic._hint_callback("ex1", "student code", failing_results)

            assert isinstance(second_hint, Awaitable)
            assert ip.run_cell.call_count == 1
            run_tests.assert_called_once()
            assert mock_stream.call_count == 1

            release_stream.set()
            assert await cast(Awaitable[bool], first_hint) is True
            assert await cast(Awaitable[bool], second_hint) is True

        assert mock_stream.call_count == 2
        mock_display.display_busy_message.assert_not_called()
        mock_display.set_hint_buttons_busy.assert_not_called()

    def test_hint_deque_truncates_at_limit(self) -> None:
        session = SessionState(hint_history_length=2)
        from notebook_ta.notebook.session import HintExchange

        for i in range(4):
            session.append_hint("ex1", HintExchange(f"code{i}", f"hint{i}"))

        history = session.get_history("ex1", 2)
        assert len(history) == 2
        assert history[-1].hint_response == "hint3"
        assert history[0].hint_response == "hint2"


class TestAnswerPostprocessor:
    """Configured hooks should receive context and replace notebook answers."""

    async def test_analysis_hook_receives_request_context(self) -> None:
        captured: list[tuple[LLMRequest, str, bool]] = []

        def hook(request: LLMRequest, answer: str, is_complete: bool) -> str:
            captured.append((request, answer, is_complete))
            return "processed final" if is_complete else "processed update"

        magic = make_magic(answer_postprocessor=hook)
        results = [TestResult("passes", True)]

        async def render_with_postprocessor(
            stream: object, *, postprocessor: object = None, **_kwargs: object
        ) -> str:
            accumulated = ""
            assert callable(postprocessor)
            async for chunk in cast(Any, stream):
                accumulated += chunk
                await cast(Any, postprocessor)(accumulated, False)
            return await cast(Any, postprocessor)(accumulated, True)

        with patch(
            "notebook_ta.notebook.magic.stream_to_output",
            side_effect=render_with_postprocessor,
        ):
            task = magic._trigger_llm("ex1", "student code", results, None)
            assert isinstance(task, Awaitable)
            assert await task == "processed final"

        assert [is_complete for _, _, is_complete in captured] == [False, True]
        request, answer, _ = captured[-1]
        assert answer == "Good feedback"
        assert request.call_type == "analysis"
        assert request.exercise_id == "ex1"
        assert request.student_code == "student code"
        assert request.test_results == tuple(results)
        assert request.provider == "ollama"
        assert request.model == "llama3.2:3b"

    async def test_processed_hint_is_saved_to_history(self) -> None:
        async def hook(
            _request: LLMRequest, answer: str, _is_complete: bool
        ) -> str:
            return answer.upper()

        magic = make_magic(answer_postprocessor=hook)
        results = [TestResult("fails", False)]

        async def render_with_postprocessor(
            stream: object, *, postprocessor: object = None, **_kwargs: object
        ) -> str:
            accumulated = ""
            assert callable(postprocessor)
            async for chunk in cast(Any, stream):
                accumulated += chunk
                await cast(Any, postprocessor)(accumulated, False)
            return await cast(Any, postprocessor)(accumulated, True)

        with patch(
            "notebook_ta.notebook.magic.stream_to_output",
            side_effect=render_with_postprocessor,
        ):
            task = magic._hint_callback("ex1", "student code", results)
            assert isinstance(task, Awaitable)
            assert await task is True

        history = magic._session.get_history("ex1", 3)
        assert history[0].hint_response == "GOOD FEEDBACK"


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
        loop = asyncio.new_event_loop()

        try:
            with (
                patch.object(magic._runner, "run", return_value=[TestResult("t", True)]),
                patch("asyncio.get_event_loop", return_value=loop),
                patch(
                    "notebook_ta.notebook.magic.stream_to_output",
                    new_callable=AsyncMock,
                ) as mock_stream,
            ):
                mock_stream.return_value = "feedback"
                magic.notebook_ta("ex1", "def add(a,b): return a+b")
        finally:
            loop.close()

        mock_display.display_debug_prompt.assert_called_once()
        call_kwargs = mock_display.display_debug_prompt.call_args
        assert call_kwargs.kwargs.get("call_type") == "analysis" or (
            len(call_kwargs.args) >= 2 and call_kwargs.args[1] == "analysis"
        )

    @patch("notebook_ta.notebook.magic.display")
    def test_debug_prompt_not_displayed_when_debug_false(self, mock_display) -> None:
        ip = make_ip_stub()
        magic = make_magic(ip=ip)  # debug defaults to False
        loop = asyncio.new_event_loop()

        try:
            with (
                patch.object(magic._runner, "run", return_value=[TestResult("t", True)]),
                patch("asyncio.get_event_loop", return_value=loop),
                patch(
                    "notebook_ta.notebook.magic.stream_to_output",
                    new_callable=AsyncMock,
                ) as mock_stream,
            ):
                mock_stream.return_value = "feedback"
                magic.notebook_ta("ex1", "def add(a,b): return a+b")
        finally:
            loop.close()

        mock_display.display_debug_prompt.assert_not_called()

    @patch("notebook_ta.notebook.magic.display")
    def test_debug_prompt_displayed_on_hint(self, mock_display) -> None:
        ip = make_ip_stub()
        magic = self._make_debug_magic(ip=ip)
        failing_results = [TestResult("t", False)]
        loop = asyncio.new_event_loop()

        try:
            with (
                patch("asyncio.get_event_loop", return_value=loop),
                patch(
                    "notebook_ta.notebook.magic.stream_to_output",
                    new_callable=AsyncMock,
                ) as mock_stream,
            ):
                mock_stream.return_value = "Hint response"
                magic._hint_callback("ex1", "student code", failing_results)
        finally:
            loop.close()

        mock_display.display_debug_prompt.assert_called_once()
        call_kwargs = mock_display.display_debug_prompt.call_args
        assert call_kwargs.kwargs.get("call_type") == "hint" or (
            len(call_kwargs.args) >= 2 and call_kwargs.args[1] == "hint"
        )
