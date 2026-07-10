"""IPython %%notebook_ta cell magic."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Coroutine
from typing import TYPE_CHECKING, Any, TypeVar, cast

from IPython.core.magic import Magics, cell_magic, magics_class

from notebook_ta.exercise.registry import ExerciseNotFoundError, ExerciseRegistry
from notebook_ta.logging import get_logger
from notebook_ta.notebook import display
from notebook_ta.notebook.session import HintExchange, SessionState
from notebook_ta.notebook.streaming import stream_to_output
from notebook_ta.testing.runner import TestRunner

if TYPE_CHECKING:
    from IPython.core.interactiveshell import InteractiveShell

    from notebook_ta.llm.base import LLMProvider
    from notebook_ta.testing.runner import TestResult

_log = get_logger("magic")
_T = TypeVar("_T")


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
        debug: bool = False,
    ) -> None:
        super().__init__(shell)
        self._registry = registry
        self._llm = llm_provider
        self._session = session
        self._runner = TestRunner()
        self._debug = debug
        self._background_tasks: set[asyncio.Task[Any]] = set()

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

        # 1. Look up the exercise before executing any student code.
        try:
            exercise = self._registry.get(exercise_id)
        except ExerciseNotFoundError:
            display.display_unavailable_message(exercise_id)
            return

        display.set_hint_buttons_busy(True)
        try:
            # 2. Execute the student's code in the user namespace.
            cast(Any, self.shell.run_cell)(cell)

            # 3. Run unit tests
            results = self._runner.run(exercise, self.shell.user_ns)
            passed_count = sum(1 for r in results if r.passed)
            _log.debug(
                "Tests complete for %r: %d/%d passed", exercise_id, passed_count, len(results)
            )

            # 4. Branch on pass/fail
            all_passed = all(r.passed for r in results)

            if all_passed:
                display.display_success()
                self._trigger_llm(exercise_id, cell, results, hint_history=None)
            else:
                display.display_test_results(results)
                display.display_hints_button(
                    exercise_id,
                    callback=lambda eid: self._hint_callback(eid, cell, results),
                )
        finally:
            display.set_hint_buttons_busy(False)

    def _trigger_llm(
        self,
        exercise_id: str,
        student_code: str,
        results: list[TestResult],
        hint_history: list[HintExchange] | None,
    ) -> Awaitable[str | None] | str | None:
        """Build a prompt and schedule LLM response streaming."""
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

        async def _run() -> str | None:
            try:
                return await stream_to_output(self._llm.stream(prompt))
            except Exception as exc:
                _log.warning("LLM stream failed for exercise %r: %s", exercise_id, exc)
                display.display_no_llm_message(exercise._global.prompts.on_no_llm)
                return None

        return self._schedule_coroutine(_run())

    def _hint_callback(
        self,
        exercise_id: str,
        student_code: str,
        test_results: list[TestResult],
    ) -> Awaitable[bool | None] | bool | None:
        """Handle a hint button click: build hint prompt, stream, and save to history."""
        exercise = self._registry.get(exercise_id)
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

        async def _run() -> bool:
            try:
                full_response = await stream_to_output(self._llm.stream(prompt))
            except Exception as exc:
                _log.warning("Hint stream failed for exercise %r: %s", exercise_id, exc)
                display.display_no_llm_message(exercise._global.prompts.on_no_llm)
                return True

            self._session.append_hint(
                exercise_id,
                HintExchange(student_code=student_code, hint_response=full_response),
            )
            return True

        return self._schedule_coroutine(_run())

    def _schedule_coroutine(self, coroutine: Coroutine[Any, Any, _T]) -> Awaitable[_T] | _T:
        """Schedule *coroutine* without blocking an already-running event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coroutine)
        task = loop.create_task(coroutine)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task


def load_ipython_extension(
    ip: InteractiveShell,
    registry: ExerciseRegistry,
    llm_provider: LLMProvider,
    session: SessionState,
    *,
    debug: bool = False,
) -> None:
    """Register the %%notebook_ta cell magic on the active IPython instance."""
    magic_instance = NotebookTAMagic(
        shell=ip,
        registry=registry,
        llm_provider=llm_provider,
        session=session,
        debug=debug,
    )
    ip.register_magics(magic_instance)
