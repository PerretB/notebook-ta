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
    "box-sizing: border-box; "
    "max-width: 100%; "
    "overflow-wrap: anywhere; "
    "word-break: break-word; "
    "color: inherit"
)
_LLM_CONTROLLED_ANSWER_STYLE = _LLM_ANSWER_STYLE.replace(
    "padding: 0.85em 1em;",
    "padding: 0.85em 4.5em 0.85em 1em;",
)

_LLM_OUTPUT_STYLE = r"""
<style>
.jp-OutputArea-output:has(.notebook-ta-llm-panel),
.jp-OutputArea-child:has(.notebook-ta-llm-panel),
.output_subarea:has(.notebook-ta-llm-panel),
.output_area:has(.notebook-ta-llm-panel),
.output_wrapper:has(.notebook-ta-llm-panel),
.cell-output:has(.notebook-ta-llm-panel),
.vscode-cell-output:has(.notebook-ta-llm-panel),
.vscode-cell-output-container:has(.notebook-ta-llm-panel),
.cell-output-ipywidget-background:has(.notebook-ta-llm-panel),
.notebook-ta-llm-panel,
.notebook-ta-llm-panel.jupyter-widgets,
.notebook-ta-llm-panel.widget-container,
.notebook-ta-llm-panel .widget-box {
    background: transparent !important;
    background-color: transparent !important;
}
.notebook-ta-llm-panel {
    position: relative !important;
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    overflow: visible !important;
}
.notebook-ta-llm-content,
.notebook-ta-llm-content.jupyter-widgets,
.notebook-ta-llm-content.widget-output {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    background: transparent !important;
    background-color: transparent !important;
}
.cell-output-ipywidget-background:has(.notebook-ta-llm-panel) {
    --jp-widgets-color: var(--vscode-editor-foreground, inherit);
    --jp-widgets-font-size: var(--vscode-editor-font-size, inherit);
}
.notebook-ta-llm-controls {
    position: absolute !important;
    top: 1.05em;
    right: 2em;
    z-index: 2;
    align-items: center;
}
.notebook-ta-llm-icon-button,
.notebook-ta-llm-icon-button.jupyter-button,
.notebook-ta-llm-icon-button.widget-button {
    width: 1.65rem !important;
    min-width: 1.65rem !important;
    height: 1.65rem !important;
    padding: 0 !important;
    border: 1px solid transparent !important;
    border-radius: 0.3rem !important;
    background: transparent !important;
    color: var(
        --vscode-editor-foreground,
        var(--jp-ui-font-color1, inherit)
    ) !important;
    font-size: 0 !important;
    line-height: 1 !important;
    opacity: 1;
}
.notebook-ta-llm-icon-button:hover,
.notebook-ta-llm-icon-button:focus-visible {
    background: rgba(220, 38, 38, 0.12) !important;
    border-color: rgba(220, 38, 38, 0.28) !important;
    color: var(--jp-error-color1, #dc2626) !important;
    opacity: 1;
}
.notebook-ta-llm-icon-button::before {
    display: block;
    font-size: 0.78rem;
    line-height: 1;
}
.notebook-ta-llm-cancel::before {
    content: "\25A0";
}
.notebook-ta-llm-cancel-all::before {
    content: "\25A0\A\25A0";
    white-space: pre;
    font-size: 0.58rem;
    line-height: 0.48rem;
}
</style>
""".strip()

_LLM_WAITING_INDICATOR = """
<style>
@keyframes notebook-ta-spin {
    to { transform: rotate(360deg); }
}
.notebook-ta-spinner {
    display: inline-block;
    width: 0.9em;
    height: 0.9em;
    border: 0.15em solid currentColor;
    border-right-color: transparent;
    border-radius: 50%;
    animation: notebook-ta-spin 0.75s linear infinite;
    vertical-align: -0.1em;
}
@media (prefers-reduced-motion: reduce) {
    .notebook-ta-spinner { animation-duration: 1.5s; }
}
</style>
<span class="notebook-ta-spinner" role="status" aria-label="Waiting for LLM response"></span>
""".strip()

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


def clear_cell_output() -> None:
    """Clear saved and live output for the currently executing notebook cell."""
    cast(Any, ipydisplay.clear_output)(wait=False)


def format_llm_answer_markdown(answer: str) -> str:
    """Wrap an LLM answer in a visually distinct Markdown block."""
    return (
        f'<div class="notebook-ta-llm-answer" style="{_LLM_CONTROLLED_ANSWER_STYLE}">\n\n'
        f'{translate("display_llm_answer_prefix")}: {answer}\n\n</div>'
    )


def format_llm_waiting_markdown() -> str:
    """Render the LLM answer block with an animated waiting indicator."""
    return format_llm_answer_markdown(_LLM_WAITING_INDICATOR)


def format_llm_queued_markdown() -> str:
    """Render the LLM answer block while its request waits in the serial queue."""
    return format_llm_answer_markdown(translate("display_llm_queued"))


class LLMOutput:
    """Own the display handle for one queued or streaming LLM response."""

    def __init__(self) -> None:
        """Create one answer panel with top-right cancellation controls."""
        import ipywidgets as widgets

        self._last_answer = ""
        self._terminal = False
        self._cancel_callback: Callable[[], object] | None = None
        self._cancel_all_callback: Callable[[], object] | None = None
        self._content = widgets.Output(
            layout=widgets.Layout(width="100%", overflow="visible"),
        )
        self._cancel_button = widgets.Button(
            description=translate("display_llm_cancel"),
            tooltip=translate("display_llm_cancel_tooltip"),
            layout=widgets.Layout(width="1.65rem", height="1.65rem"),
        )
        self._cancel_button.add_class("notebook-ta-llm-icon-button")
        self._cancel_button.add_class("notebook-ta-llm-cancel")
        self._cancel_all_button = widgets.Button(
            description=translate("display_llm_cancel_all"),
            tooltip=translate("display_llm_cancel_all_tooltip"),
            layout=widgets.Layout(width="1.65rem", height="1.65rem"),
        )
        self._cancel_all_button.add_class("notebook-ta-llm-icon-button")
        self._cancel_all_button.add_class("notebook-ta-llm-cancel-all")
        self._cancel_button.on_click(self._cancel_request)
        self._cancel_all_button.on_click(self._cancel_all_requests)
        self._controls = widgets.Box(
            [self._cancel_button, self._cancel_all_button],
            layout=widgets.Layout(display="flex"),
        )
        self._controls.add_class("notebook-ta-llm-controls")
        self._cancel_all_button.layout.margin = "0 0 0 0.15rem"
        self._content.add_class("notebook-ta-llm-content")
        self._panel = widgets.Box(
            [self._content, self._controls],
            layout=widgets.Layout(width="100%", overflow="visible"),
        )
        self._panel.add_class("notebook-ta-llm-panel")
        self.update_markdown(format_llm_queued_markdown())
        cast(Any, ipydisplay.display)(cast(Any, ipydisplay.HTML)(_LLM_OUTPUT_STYLE))
        cast(Any, ipydisplay.display)(self._panel)

    def bind_cancellation(
        self,
        cancel_request: Callable[[], object],
        cancel_all: Callable[[], object],
    ) -> None:
        """Connect this output's controls to its dispatcher callbacks."""
        self._cancel_callback = cancel_request
        self._cancel_all_callback = cancel_all

    def show_waiting(self) -> None:
        """Show that this request has reached the front of the queue."""
        if self._terminal:
            return
        self.update_markdown(format_llm_waiting_markdown())

    def show_answer(self, answer: str) -> None:
        """Render an accumulated or completed LLM answer."""
        if self._terminal:
            return
        self._last_answer = answer
        self.update_markdown(format_llm_answer_markdown(answer))

    def show_unavailable(self, message: str) -> None:
        """Render an LLM failure in this request's original output area."""
        content = (
            f"**{translate('display_llm_unavailable_heading')}**\n\n{message}"
        )
        self._show_terminal(content)

    def show_failed(self, detail: str) -> None:
        """Render an unexpected dispatcher failure and finalize the controls."""
        content = translate(
            "display_llm_failed",
            {"detail": html.escape(detail)},
        )
        self._show_terminal(content)

    def show_cancelled(self) -> None:
        """Render cancellation while preserving any partial streamed response."""
        key = "display_llm_cancelled_partial" if self._last_answer else "display_llm_cancelled"
        content = translate(key)
        if self._last_answer:
            content = f"{content}\n\n{self._last_answer}"
        self._show_terminal(content)

    def mark_completed(self) -> None:
        """Mark a successfully rendered response as terminal and hide its controls."""
        self._terminal = True
        self._hide_controls()

    def update_markdown(self, content: str) -> None:
        """Replace the Markdown bundle inside this response's composite widget."""
        self._content.outputs = (
            {
                "output_type": "display_data",
                "data": {"text/markdown": content, "text/plain": content},
                "metadata": {},
            },
        )

    def _show_terminal(self, content: str) -> None:
        """Render terminal content once and disable further request updates."""
        if self._terminal:
            return
        self._terminal = True
        self.update_markdown(format_llm_answer_markdown(content))
        self._hide_controls()

    def _hide_controls(self) -> None:
        """Disable and hide both cancellation controls."""
        self._cancel_button.disabled = True
        self._cancel_all_button.disabled = True
        self._controls.layout.display = "none"

    def _cancel_request(self, _event: object) -> None:
        """Invoke the bound callback for this request."""
        if not self._terminal and self._cancel_callback is not None:
            self._cancel_callback()

    def _cancel_all_requests(self, _event: object) -> None:
        """Invoke the bound callback for every outstanding request."""
        if not self._terminal and self._cancel_all_callback is not None:
            self._cancel_all_callback()


class InitializationDisplay:
    """Render all initialization updates through one Markdown display handle."""

    def __init__(self) -> None:
        """Create the shared display using the exact LLM-answer presentation."""
        self._rows: dict[str, str] = {}
        self._handle = cast(Any, ipydisplay.display)(
            cast(Any, ipydisplay.Markdown)(self._format()),
            display_id=True,
        )

    def _format(self) -> str:
        """Format the panel with the same inline style used for LLM answers."""
        title = html.escape(translate("initialization_title"))
        rows = "".join(
            f'<div style="margin: 0.2em 0">{row}</div>' for row in self._rows.values()
        )
        return (
            f'<div style="{_LLM_ANSWER_STYLE}">\n\n'
            f"<strong>{title}</strong>{rows}\n\n</div>"
        )

    def _render(self) -> None:
        """Refresh the combined status content in place."""
        if self._handle is not None:
            self._handle.update(cast(Any, ipydisplay.Markdown)(self._format()))

    def show_hardware(
        self,
        ram_gb: float,
        gpu_name: str | None,
        vram_gb: float,
        model_name: str | None,
        model_description: str | None,
    ) -> None:
        """Add the hardware detection and model-selection result."""
        gpu = (
            translate(
                "initialization_gpu",
                {"gpu_name": html.escape(gpu_name), "vram_gb": vram_gb},
            )
            if gpu_name
            else ""
        )
        key = "initialization_hardware" if model_name is not None else "initialization_no_model"
        values = {"ram_gb": ram_gb, "gpu_text": gpu}
        if model_name is not None:
            values.update(
                {
                    "model_name": html.escape(model_name),
                    "model_description": html.escape(model_description or ""),
                }
            )
        self._rows["hardware"] = translate(key, values)
        self._render()

    def update_ollama(self, state: str, detail: str | None = None) -> None:
        """Update the Ollama initialization row."""
        running_states = {
            "checking_server",
            "starting_server",
            "checking_model",
            "pulling_model",
        }
        message = translate(f"ollama_setup_{state}")
        if detail:
            message = f"{message} <small>({html.escape(detail)})</small>"
        spinner = f"{_LLM_WAITING_INDICATOR} " if state in running_states else ""
        self._rows["ollama"] = f"{spinner}{message}"
        self._render()

    def show_loaded(self, provider: str, model: str, exercise_count: int) -> None:
        """Add the final successfully-loaded summary."""
        self._rows["loaded"] = translate(
            "initialization_loaded",
            {
                "provider": html.escape(provider),
                "model": html.escape(model),
                "exercise_count": exercise_count,
            },
        )
        self._render()


def display_initialization() -> InitializationDisplay:
    """Display and return the shared notebook-ta initialization panel."""
    return InitializationDisplay()


def display_ollama_setup() -> Callable[[str, str | None], None]:
    """Show a standalone Ollama setup panel and return its update callback."""
    import ipywidgets as widgets

    status = widgets.HTML()
    running_states = {
        "checking_server",
        "starting_server",
        "checking_model",
        "pulling_model",
    }

    def update(state: str, detail: str | None = None) -> None:
        """Update the setup panel with a localized state and optional backend detail."""
        message = translate(f"ollama_setup_{state}")
        if detail:
            message = f"{message} <small>({html.escape(detail)})</small>"
        spinner = f"{_LLM_WAITING_INDICATOR} " if state in running_states else ""
        status.value = (
            '<div style="padding: 0.65em 0.85em; border-left: 4px solid #14b8a6; '
            'background: rgba(20, 184, 166, 0.10); border-radius: 6px">'
            f"{spinner}{message}</div>"
        )

    update("checking_server")
    cast(Any, ipydisplay.display)(status)
    return update


def display_success() -> None:
    """Show a 'tests passed' indicator before streaming begins."""
    cast(Any, ipydisplay.display)(cast(Any, ipydisplay.Markdown)(translate("display_success")))


def display_execution_failure(error: BaseException) -> None:
    """Show that student-code execution failed before tests could run.

    Args:
        error: Compilation or runtime error reported by IPython.
    """
    detail = html.escape(f"{type(error).__name__}: {error}")
    content = (
        f'<h3 style="margin-bottom: 0.4em">{translate("display_execution_failure_heading")}</h3>'
        f'<div style="white-space: pre-wrap; font-family: monospace">{detail}</div>'
        f'<p>{translate("display_execution_failure_detail")}</p>'
    )
    cast(Any, ipydisplay.display)(cast(Any, ipydisplay.HTML)(content))


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
