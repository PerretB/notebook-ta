"""Notebook display helpers using IPython.display and ipywidgets."""

from __future__ import annotations

import asyncio
import html
import inspect
import weakref
from collections.abc import Awaitable, Callable, Coroutine
from typing import TYPE_CHECKING, Any, cast

from IPython import display as ipydisplay

from notebook_ta.i18n import translate
from notebook_ta.notebook._ansi import ansi_to_html

if TYPE_CHECKING:
    from notebook_ta.testing.runner import TestResult

_LLM_ANSWER_STYLE = (
    "background: rgba(20, 184, 166, 0.14); "
    "border-left: 4px solid #14b8a6; "
    "border-radius: 6px; "
    "padding: 0.85em 1em; "
    "margin: 0.75em 0; "
    "color: inherit"
)

_HINT_BUTTON_STYLE = """
<style>
.jp-OutputArea-output:has(.notebook-ta-hints),
.jp-OutputArea-child:has(.notebook-ta-hints),
.output_subarea:has(.notebook-ta-hints),
.output_area:has(.notebook-ta-hints),
.output_wrapper:has(.notebook-ta-hints),
.cell-output:has(.notebook-ta-hints),
.vscode-cell-output:has(.notebook-ta-hints),
.vscode-cell-output-container:has(.notebook-ta-hints),
.cell-output-ipywidget-background:has(.notebook-ta-hints),
.notebook-ta-hints,
.notebook-ta-hints.jupyter-widgets,
.notebook-ta-hints.widget-container,
.notebook-ta-hints .widget-box {
    background: transparent !important;
    background-color: transparent !important;
}

.cell-output-ipywidget-background:has(.notebook-ta-hints) {
    --jp-widgets-color: var(--vscode-editor-foreground, inherit);
    --jp-widgets-font-size: var(--vscode-editor-font-size, inherit);
}

.notebook-ta-hint-button,
.notebook-ta-hint-button button,
.notebook-ta-hints .widget-button {
    background: var(--jp-brand-color1, #0f766e) !important;
    color: var(--jp-ui-inverse-font-color1, #ffffff) !important;
    border-color: var(--jp-brand-color0, #0d9488) !important;
}

.notebook-ta-hint-button:hover,
.notebook-ta-hint-button button:hover,
.notebook-ta-hints .widget-button:hover {
    background: var(--jp-brand-color0, #0d9488) !important;
}
</style>
""".strip()
_HINT_BUTTONS_BUSY = False
_HINT_BUTTONS: list[weakref.ReferenceType[Any]] = []
_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


def _schedule_background_task(coroutine: Coroutine[Any, Any, None]) -> None:
    """Keep a background display task alive until it completes."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(coroutine)
        return

    task = loop.create_task(coroutine)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


def _apply_hint_button_state(button: Any) -> None:
    """Apply the current global busy state to a registered hint button."""
    button.disabled = _HINT_BUTTONS_BUSY
    button.description = (
        translate("display_hints_busy_button")
        if _HINT_BUTTONS_BUSY
        else translate("display_hints_button")
    )


def _live_hint_buttons() -> list[Any]:
    """Return currently live hint button widgets and prune stale references."""
    live_buttons: list[Any] = []
    live_refs: list[weakref.ReferenceType[Any]] = []
    for button_ref in _HINT_BUTTONS:
        button = button_ref()
        if button is not None:
            live_buttons.append(button)
            live_refs.append(button_ref)
    _HINT_BUTTONS[:] = live_refs
    return live_buttons


def set_hint_buttons_busy(is_busy: bool) -> None:
    """Disable or enable all registered hint buttons for notebook-ta operations."""
    global _HINT_BUTTONS_BUSY
    _HINT_BUTTONS_BUSY = is_busy
    for button in _live_hint_buttons():
        _apply_hint_button_state(button)


def hints_are_busy() -> bool:
    """Return whether hint buttons are globally disabled because notebook-ta is busy."""
    return _HINT_BUTTONS_BUSY


def format_llm_answer_markdown(answer: str) -> str:
    """Wrap an LLM answer in a visually distinct Markdown block."""
    return (
        f'<div style="{_LLM_ANSWER_STYLE}">\n\n'
        f'{translate("display_llm_answer_prefix")}: {answer}\n\n</div>'
    )


def display_success() -> None:
    """Show a 'tests passed' indicator before streaming begins."""
    cast(Any, ipydisplay.display)(cast(Any, ipydisplay.Markdown)(translate("display_success")))


def display_test_results(results: list[TestResult]) -> None:
    """Render a formatted list of test results.

    Args:
        results: List of TestResult objects.
    """
    result_blocks: list[str] = []
    for result in results:
        icon = "✅" if result.passed else "❌"
        message = ""
        if result.message:
            message = (
                '<div style="margin: 0.25em 0 0 1.5em; white-space: pre-wrap; '
                f'font-family: monospace">{ansi_to_html(result.message)}</div>'
            )
        result_blocks.append(
            f'<div style="margin: 0.35em 0">{icon} '
            f"<strong>{html.escape(str(result.name))}</strong>{message}</div>"
        )
    content = (
        f'<h3 style="margin-bottom: 0.4em">{translate("display_test_results_heading")}</h3>'
        + "".join(result_blocks)
    )
    cast(Any, ipydisplay.display)(cast(Any, ipydisplay.HTML)(content))


def display_hints_button(
    exercise_id: str,
    callback: Callable[[str], Awaitable[bool | None] | bool | None],
) -> None:
    """Render an interactive 'Give me hints' button.

    Args:
        exercise_id: The exercise ID passed to the callback.
        callback: Called with exercise_id when the button is clicked. Returning
            ``False`` means the request was ignored because notebook-ta is busy.
            Awaitable results keep the button disabled until the request finishes.
    """
    import ipywidgets as widgets

    button = widgets.Button(
        description=translate("display_hints_button"),
        tooltip=translate("display_hints_tooltip"),
        layout=widgets.Layout(width="auto"),
    )
    button.style.button_color = "var(--jp-brand-color1, #0f766e)"
    button.style.text_color = "var(--jp-ui-inverse-font-color1, #ffffff)"
    button.add_class("notebook-ta-hint-button")
    status = widgets.HTML(value="", layout=widgets.Layout(margin="0 0 0 0.5em"))
    _HINT_BUTTONS.append(weakref.ref(button))
    _apply_hint_button_state(button)

    def _restore_button() -> None:
        if _HINT_BUTTONS_BUSY:
            _apply_hint_button_state(button)
            return
        button.disabled = False
        button.description = translate("display_hints_button")

    def _apply_result(accepted: bool | None) -> None:
        if accepted is False:
            status.value = (
                '<span style="color: var(--jp-warn-color1, #b45309)">'
                f"{translate('display_hints_busy_status')}</span>"
            )
        else:
            status.value = ""

    def _on_click(_event: object) -> None:
        if _HINT_BUTTONS_BUSY:
            _apply_hint_button_state(button)
            return
        button.disabled = True
        button.description = translate("display_hints_fetching")
        accepted: Awaitable[bool | None] | bool | None = None
        try:
            accepted = callback(exercise_id)
            if inspect.isawaitable(accepted):
                async def _finish_async_request() -> None:
                    try:
                        _apply_result(await accepted)
                    finally:
                        _restore_button()

                _schedule_background_task(_finish_async_request())
                return
            _apply_result(accepted)
        finally:
            if not inspect.isawaitable(accepted):
                _restore_button()

    button.on_click(_on_click)
    container = widgets.Box(
        [button, status],
        layout=widgets.Layout(
            align_items="center",
            display="inline-flex",
            width="auto",
        ),
    )
    container.add_class("notebook-ta-hints")
    cast(Any, ipydisplay.display)(cast(Any, ipydisplay.HTML)(_HINT_BUTTON_STYLE))
    cast(Any, ipydisplay.display)(container)


def display_no_llm_message(message: str) -> None:
    """Render the configured no-LLM fallback message as Markdown.

    Args:
        message: The ``prompts.on_no_llm`` string from the global config.
    """
    cast(Any, ipydisplay.display)(
        cast(Any, ipydisplay.Markdown)(
            f"**{translate('display_llm_unavailable_heading')}**\n\n{message}"
        )
    )


def display_unavailable_message(exercise_id: str) -> None:
    """Render a warning when an exercise ID is not found in the registry.

    Args:
        exercise_id: The unrecognised exercise identifier.
    """
    cast(Any, ipydisplay.display)(
        cast(Any, ipydisplay.Markdown)(
            translate("display_unavailable", {"exercise_id": exercise_id})
        )
    )


def display_busy_message() -> None:
    """Render a warning when notebook-ta is already processing another request."""
    cast(Any, ipydisplay.display)(
        cast(Any, ipydisplay.Markdown)(translate("display_busy"))
    )


def display_debug_prompt(prompt: str, call_type: str = "analysis") -> None:
    """Render the LLM prompt in a collapsible accordion widget for debugging.

    Displayed only when ``notebook_ta.load()`` is called with ``debug=True``.
    The accordion starts closed so the prompt wall-of-text does not overwhelm
    the notebook output by default.

    Args:
        prompt: The full prompt string that will be sent to the LLM.
        call_type: Human-readable label for the prompt type, e.g. ``"analysis"``
                   or ``"hint"``.
    """
    import ipywidgets as widgets

    textarea = widgets.Textarea(
        value=prompt,
        layout=widgets.Layout(width="100%", height="200px"),
        disabled=True,
    )
    accordion = widgets.Accordion(children=[textarea])
    accordion.set_title(0, translate("debug_prompt_title", {"call_type": call_type}))
    accordion.selected_index = None  # start closed
    cast(Any, ipydisplay.display)(accordion)
