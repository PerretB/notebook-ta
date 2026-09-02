"""IPython %%notebook_ta cell magic."""

from __future__ import annotations

import atexit
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Literal, cast

from IPython.core.magic import Magics, cell_magic, magics_class

from notebook_ta.exercise.registry import ExerciseNotFoundError, ExerciseRegistry
from notebook_ta.i18n import translate
from notebook_ta.llm.base import LLMProvider
from notebook_ta.logging import get_logger
from notebook_ta.notebook import display
from notebook_ta.notebook.dispatcher import LLMDispatcher
from notebook_ta.notebook.session import HintExchange, SessionState
from notebook_ta.notebook.streaming import stream_to_output
from notebook_ta.testing.runner import TestRunner

if TYPE_CHECKING:
    from IPython.core.interactiveshell import InteractiveShell

    from notebook_ta.llm.postprocessing import AnswerPostprocessor
    from notebook_ta.testing.runner import TestResult

_log = get_logger("magic")
_active_magic_instance: NotebookTAMagic | None = None


@magics_class
class NotebookTAMagic(Magics):
    """IPython magic class providing the %%notebook_ta cell magic."""

    def __init__(
        self,
        shell: InteractiveShell | None,
        registry: ExerciseRegistry,
        llm_provider: LLMProvider,
        session: SessionState,
        *,
        answer_postprocessor: AnswerPostprocessor | None = None,
        debug: bool = False,
    ) -> None:
        super().__init__(shell)
        self._registry = registry
        self._llm = llm_provider
        self._session = session
        self._answer_postprocessor = answer_postprocessor
        self._runner = TestRunner()
        self._debug = debug
        self._dispatcher = LLMDispatcher()
        atexit.register(self.shutdown_now)

    @cell_magic
    def notebook_ta(self, line: str, cell: str) -> None:
        """Cell magic: run unit tests and stream LLM feedback.

        Usage::

            %%notebook_ta <exercise_id>
            # student code here
        """
        exercise_id = line.strip()
        _log.debug("Cell magic invoked for exercise %r", exercise_id)
        assert self.shell is not None
        display.clear_cell_output()

        # 1. Look up the exercise before executing any student code.
        try:
            exercise = self._registry.get(exercise_id)
        except ExerciseNotFoundError:
            display.display_unavailable_message(exercise_id)
            return

        if exercise.answer_type == "free_text":
            if not cell.strip():
                _log.error(
                    translate("magic_student_answer_empty", language=exercise.language)
                )
                return
            self._trigger_llm(
                exercise_id,
                cell,
                results=None,
                hint_history=None,
            )
            return

        # 2. Execute the student's code in the user namespace.
        execution_result = cast(Any, self.shell.run_cell)(cell)
        execution_error = execution_result.error_before_exec or execution_result.error_in_exec
        if execution_error is not None:
            _log.debug(
                "Student code execution failed for %r: %s",
                exercise_id,
                execution_error,
            )
            display.display_execution_failure(execution_error)
            return

        # 3. Run tests before later notebook cells can mutate the user namespace.
        results = self._runner.run(exercise, self.shell.user_ns)
        passed_count = sum(1 for result in results if result.passed)
        _log.debug(
            "Tests complete for %r: %d/%d passed", exercise_id, passed_count, len(results)
        )

        if self._reject_oversized_answer(exercise_id, cell):
            display.display_test_results(results)
            return

        # 4. Render the test outcome, then queue any LLM work independently.
        if all(result.passed for result in results):
            display.display_success()
            self._trigger_llm(
                exercise_id,
                cell,
                results,
                hint_history=None,
            )
        else:
            display.display_test_results(results)
            display.display_hints_button(
                exercise_id,
                callback=lambda eid: self._hint_callback(eid, cell, results),
            )

    def _trigger_llm(
        self,
        exercise_id: str,
        student_code: str,
        results: list[TestResult] | None,
        hint_history: list[HintExchange] | None,
    ) -> Awaitable[str | None] | str | None:
        """Build a prompt and schedule LLM response streaming."""
        if self._reject_oversized_answer(exercise_id, student_code):
            return None

        if not self._llm.is_available():
            exercise = self._registry.get(exercise_id)
            display.display_no_llm_message(
                exercise._global.prompts.on_no_llm
            )
            return None

        exercise = self._registry.get(exercise_id)
        prompt = exercise.build_prompt(
            student_code=student_code,
            test_results=results,
            hint_history=hint_history,
        )
        _log.debug(
            "Sending analysis prompt to LLM: exercise=%r, prompt_len=%d",
            exercise_id,
            len(prompt),
        )
        if self._debug:
            display.display_debug_prompt(prompt, call_type="analysis")

        output = display.LLMOutput()

        async def _run() -> str | None:
            try:
                return await self._stream_answer(
                    exercise_id=exercise_id,
                    call_type="analysis",
                    prompt=prompt,
                    student_code=student_code,
                    test_results=results,
                    hint_history=hint_history,
                    output=output,
                )
            except Exception as exc:
                _log.warning("LLM stream failed for exercise %r: %s", exercise_id, exc)
                output.show_unavailable(exercise._global.prompts.on_no_llm)
                return None

        return self._dispatcher.enqueue(_run, output)

    def _hint_callback(
        self,
        exercise_id: str,
        student_code: str,
        test_results: list[TestResult],
    ) -> Awaitable[bool | None] | bool | None:
        """Queue a hint request and save its response to history when complete."""
        return self._start_hint_request(exercise_id, student_code, test_results)

    def _start_hint_request(
        self,
        exercise_id: str,
        student_code: str,
        test_results: list[TestResult],
    ) -> Awaitable[bool | None] | bool | None:
        """Build, schedule, and record an accepted hint request."""
        exercise = self._registry.get(exercise_id)
        if self._reject_oversized_answer(exercise_id, student_code):
            return True

        hint_history = self._session.get_history(
            exercise_id,
            exercise._global.prompts.hint_history_length,
        )

        if not self._llm.is_available():
            display.display_no_llm_message(exercise._global.prompts.on_no_llm)
            return True

        _log.debug("Hint requested for exercise %r", exercise_id)
        prompt = exercise.build_prompt(
            student_code=student_code,
            test_results=test_results,
            hint_history=hint_history if hint_history else [],
        )
        _log.debug(
            "Sending hint prompt to LLM: exercise=%r, prompt_len=%d", exercise_id, len(prompt)
        )
        if self._debug:
            display.display_debug_prompt(prompt, call_type="hint")

        output = display.LLMOutput()

        async def _run() -> bool:
            try:
                full_response = await self._stream_answer(
                    exercise_id=exercise_id,
                    call_type="hint",
                    prompt=prompt,
                    student_code=student_code,
                    test_results=test_results,
                    hint_history=hint_history,
                    output=output,
                )
            except Exception as exc:
                _log.warning("Hint stream failed for exercise %r: %s", exercise_id, exc)
                output.show_unavailable(exercise._global.prompts.on_no_llm)
                return True

            self._session.append_hint(
                exercise_id,
                HintExchange(student_code=student_code, hint_response=full_response),
            )
            return True

        return self._dispatcher.enqueue(_run, output)

    async def _stream_answer(
        self,
        *,
        exercise_id: str,
        call_type: Literal["analysis", "hint"],
        prompt: str,
        student_code: str,
        test_results: list[TestResult] | None,
        hint_history: list[HintExchange] | None,
        output: display.LLMOutput,
    ) -> str:
        """Stream an answer, applying the configured hook to every accumulated update."""
        stream_postprocessor: Callable[[str, bool], Awaitable[str]] | None = None
        if self._answer_postprocessor is not None:
            from notebook_ta.llm.postprocessing import LLMRequest, postprocess_answer

            exercise = self._registry.get(exercise_id)
            request = LLMRequest(
                call_type=call_type,
                exercise_id=exercise_id,
                prompt=prompt,
                student_code=student_code,
                test_results=tuple(test_results or ()),
                hint_history=tuple(hint_history or ()),
                provider=exercise._global.llm.provider,
                model=exercise._global.llm.model,
                temperature=exercise._global.llm.temperature,
                answer_type=exercise.answer_type,
            )

            async def _postprocess_update(answer: str, is_complete: bool) -> str:
                """Apply the configured postprocessor to an accumulated answer update."""
                assert self._answer_postprocessor is not None
                return await postprocess_answer(
                    self._answer_postprocessor,
                    request,
                    answer,
                    is_complete,
                )

            stream_postprocessor = _postprocess_update

        response_stream = (
            self._llm.stream_response(prompt)
            if self._debug and isinstance(self._llm, LLMProvider)
            else self._llm.stream(prompt)
        )
        if stream_postprocessor is None:
            if self._debug:
                return await stream_to_output(
                    response_stream,
                    show_thinking=True,
                    output=output,
                )
            return await stream_to_output(response_stream, output=output)
        if not self._debug:
            return await stream_to_output(
                response_stream,
                postprocessor=stream_postprocessor,
                output=output,
            )
        return await stream_to_output(
            response_stream,
            postprocessor=stream_postprocessor,
            show_thinking=True,
            output=output,
        )

    def _reject_oversized_answer(self, exercise_id: str, student_code: str) -> bool:
        """Emit an error and reject LLM use when a student answer exceeds its limit."""
        exercise = self._registry.get(exercise_id)
        answer_length = len(student_code)
        if answer_length <= exercise.max_student_answer_length:
            return False
        _log.error(
            translate(
                (
                    "magic_free_text_answer_too_long"
                    if exercise.answer_type == "free_text"
                    else "magic_student_answer_too_long"
                ),
                {
                    "answer_length": answer_length,
                    "max_length": exercise.max_student_answer_length,
                },
                language=exercise.language,
            )
        )
        return True

    def shutdown_now(self) -> None:
        """Cancel this magic instance's LLM work during reload or interpreter exit."""
        self._dispatcher.shutdown_now()

def load_ipython_extension(
    ip: InteractiveShell,
    registry: ExerciseRegistry,
    llm_provider: LLMProvider,
    session: SessionState,
    *,
    answer_postprocessor: AnswerPostprocessor | None = None,
    debug: bool = False,
) -> None:
    """Register the %%notebook_ta cell magic on the active IPython instance."""
    global _active_magic_instance
    if _active_magic_instance is not None:
        _active_magic_instance.shutdown_now()
    magic_instance = NotebookTAMagic(
        shell=ip,
        registry=registry,
        llm_provider=llm_provider,
        session=session,
        answer_postprocessor=answer_postprocessor,
        debug=debug,
    )
    ip.register_magics(magic_instance)
    _active_magic_instance = magic_instance
