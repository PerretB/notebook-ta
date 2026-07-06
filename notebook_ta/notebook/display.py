"""Notebook display helpers using IPython.display and ipywidgets."""

from __future__ import annotations

from typing import Callable

from IPython import display as ipydisplay


def display_success() -> None:
    """Show a 'tests passed' indicator before streaming begins."""
    ipydisplay.display(ipydisplay.Markdown("✅ **All tests passed!** Generating analysis…"))


def display_test_results(results: list) -> None:
    """Render a formatted list of test results.

    Args:
        results: List of TestResult objects.
    """
    lines: list[str] = ["### Test Results\n"]
    for result in results:
        icon = "✅" if result.passed else "❌"
        lines.append(f"{icon} **{result.name}**")
        if result.message:
            formatted_msg = result.message.replace("\n", "  \n> ")
            lines.append(f"  \n> {formatted_msg}")
        lines.append("")
    ipydisplay.display(ipydisplay.Markdown("\n".join(lines)))


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
