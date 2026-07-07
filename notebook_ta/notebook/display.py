"""Notebook display helpers using IPython.display and ipywidgets."""

from __future__ import annotations

import html
import re
from collections.abc import Callable

from IPython import display as ipydisplay

_ANSI_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")
_ANSI_COLORS = {
    30: "#000000",
    31: "#aa0000",
    32: "#00aa00",
    33: "#aa5500",
    34: "#0000aa",
    35: "#aa00aa",
    36: "#00aaaa",
    37: "#aaaaaa",
    90: "#555555",
    91: "#ff5555",
    92: "#00c000",
    93: "#d4a000",
    94: "#5555ff",
    95: "#ff55ff",
    96: "#00b8b8",
    97: "#ffffff",
}


def _ansi_to_html(value: str) -> str:
    """Convert common ANSI SGR sequences to escaped inline HTML."""
    parts: list[str] = []
    position = 0
    bold = False
    underline = False
    color: str | None = None
    span_open = False

    for match in _ANSI_SGR_RE.finditer(value):
        parts.append(html.escape(value[position : match.start()]))
        if span_open:
            parts.append("</span>")

        codes = [int(code) if code else 0 for code in match.group(1).split(";")]
        for code in codes:
            if code == 0:
                bold = False
                underline = False
                color = None
            elif code == 1:
                bold = True
            elif code == 4:
                underline = True
            elif code == 22:
                bold = False
            elif code == 24:
                underline = False
            elif code == 39:
                color = None
            elif code in _ANSI_COLORS:
                color = _ANSI_COLORS[code]

        styles: list[str] = []
        if color:
            styles.append(f"color: {color}")
        if bold:
            styles.append("font-weight: bold")
        if underline:
            styles.append("text-decoration: underline")
        if styles:
            parts.append(f'<span style="{"; ".join(styles)}">')
            span_open = True
        else:
            span_open = False
        position = match.end()

    parts.append(html.escape(value[position:]))
    if span_open:
        parts.append("</span>")
    return "".join(parts)


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
                f'font-family: monospace">{_ansi_to_html(result.message)}</div>'
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
        button_style="info",
        tooltip="Ask the LLM for targeted hints",
        layout=widgets.Layout(width="auto"),
    )

    def _on_click(_event: object) -> None:
        button.disabled = True
        button.description = "⏳ Fetching hints…"
        try:
            callback(exercise_id)
        finally:
            button.disabled = False
            button.description = "💡 Give me hints"

    button.on_click(_on_click)
    ipydisplay.display(button)


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
