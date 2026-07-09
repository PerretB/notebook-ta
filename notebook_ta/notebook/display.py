"""Notebook display helpers using IPython.display and ipywidgets."""

from __future__ import annotations

import html
from collections.abc import Callable

from IPython import display as ipydisplay

from notebook_ta.notebook._ansi import ansi_to_html

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


def format_llm_answer_markdown(answer: str) -> str:
    """Wrap an LLM answer in a visually distinct Markdown block."""
    return f'<div style="{_LLM_ANSWER_STYLE}">\n\n🤖 {answer}\n\n</div>'


def display_success() -> None:
    """Show a 'tests passed' indicator before streaming begins."""
    ipydisplay.display(ipydisplay.Markdown("✅ **All tests passed!** Generating analysis…"))


def display_test_results(results: list) -> None:
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
    content = '<h3 style="margin-bottom: 0.4em">Test Results</h3>' + "".join(result_blocks)
    ipydisplay.display(ipydisplay.HTML(content))


def display_hints_button(
    exercise_id: str,
    callback: Callable[[str], None],
) -> None:
    """Render an interactive 'Give me hints' button.

    Args:
        exercise_id: The exercise ID passed to the callback.
        callback: Called with exercise_id when the button is clicked.
    """
    import ipywidgets as widgets

    button = widgets.Button(
        description="💡 Give me hints",
        tooltip="Ask the LLM for targeted hints",
        layout=widgets.Layout(width="auto"),
    )
    button.style.button_color = "var(--jp-brand-color1, #0f766e)"
    button.style.text_color = "var(--jp-ui-inverse-font-color1, #ffffff)"
    button.add_class("notebook-ta-hint-button")

    def _on_click(_event: object) -> None:
        button.disabled = True
        button.description = "⏳ Fetching hints…"
        try:
            callback(exercise_id)
        finally:
            button.disabled = False
            button.description = "💡 Give me hints"

    button.on_click(_on_click)
    container = widgets.Box(
        [button],
        layout=widgets.Layout(display="inline-flex", width="auto"),
    )
    container.add_class("notebook-ta-hints")
    ipydisplay.display(ipydisplay.HTML(_HINT_BUTTON_STYLE))
    ipydisplay.display(container)


def display_no_llm_message(message: str) -> None:
    """Render the configured no-LLM fallback message as Markdown.

    Args:
        message: The ``prompts.on_no_llm`` string from the global config.
    """
    ipydisplay.display(ipydisplay.Markdown(f"⚠️ **LLM unavailable**\n\n{message}"))


def display_unavailable_message(exercise_id: str) -> None:
    """Render a warning when an exercise ID is not found in the registry.

    Args:
        exercise_id: The unrecognised exercise identifier.
    """
    ipydisplay.display(
        ipydisplay.Markdown(
            f"⚠️ **Exercise `{exercise_id}` not found.**\n\n"
            "Please check the exercise ID in the magic line and ensure "
            "`notebook_ta.load()` has been called with the correct exercises file."
        )
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
    accordion.set_title(0, f"🐛 Debug – LLM Prompt ({call_type})")
    accordion.selected_index = None  # start closed
    ipydisplay.display(accordion)
