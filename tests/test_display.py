"""Tests for notebook display helpers."""

from __future__ import annotations

from unittest.mock import patch

from IPython import display as ipydisplay

from notebook_ta.notebook.display import (
    display_hints_button,
    display_test_results,
    format_llm_answer_markdown,
)
from notebook_ta.testing.runner import TestResult as RunnerResult


def test_display_test_results_converts_ansi_styles_to_html() -> None:
    """ANSI colors and text styles should render as HTML, not control characters."""
    result = RunnerResult(
        name="custom test",
        passed=True,
        message="\033[92m✔ 2/2 tests passed.\033[0m\n\033[1;4mDetails\033[0m",
    )

    with patch("notebook_ta.notebook.display.ipydisplay.display") as display_mock:
        display_test_results([result])

    rendered = display_mock.call_args.args[0]
    assert isinstance(rendered, ipydisplay.HTML)
    assert "\033[" not in rendered.data
    assert "color: #00c000" in rendered.data
    assert "font-weight: bold" in rendered.data
    assert "text-decoration: underline" in rendered.data
    assert "✔ 2/2 tests passed." in rendered.data


def test_display_test_results_escapes_test_content() -> None:
    """Test names and messages should not inject arbitrary notebook HTML."""
    result = RunnerResult(name="<name>", passed=False, message="expected <b>, got &")

    with patch("notebook_ta.notebook.display.ipydisplay.display") as display_mock:
        display_test_results([result])

    rendered = display_mock.call_args.args[0]
    assert "&lt;name&gt;" in rendered.data
    assert "expected &lt;b&gt;, got &amp;" in rendered.data


def test_format_llm_answer_markdown_wraps_answer() -> None:
    """LLM answers should be visually separated from the original notebook content."""
    rendered = format_llm_answer_markdown("Nice work.")

    assert rendered.startswith('<div style="background: rgba(20, 184, 166, 0.14);')
    assert "color: inherit" in rendered
    assert "🤖 Nice work." in rendered
    assert rendered.endswith("</div>")


def test_display_hints_button_uses_theme_aware_transparent_container() -> None:
    """Hint button output should not force a white background in notebook themes."""
    with patch("notebook_ta.notebook.display.ipydisplay.display") as display_mock:
        display_hints_button("exercise-id", callback=lambda _exercise_id: None)

    assert display_mock.call_count == 2
    style_output, button_output = [call.args[0] for call in display_mock.call_args_list]

    assert isinstance(style_output, ipydisplay.HTML)
    assert "notebook-ta-hints" in style_output.data
    assert "background: transparent" in style_output.data
    assert "background-color: transparent" in style_output.data
    assert ".jp-OutputArea-output" in style_output.data
    assert ".output_area" in style_output.data
    assert ".cell-output-ipywidget-background:has(.notebook-ta-hints)" in style_output.data
    assert "--jp-widgets-color: var(--vscode-editor-foreground, inherit)" in style_output.data
    assert ":root" not in style_output.data
    assert "--jp-brand-color1" in style_output.data

    assert "notebook-ta-hints" in button_output._dom_classes
    button = button_output.children[0]
    assert button.style.button_color == "var(--jp-brand-color1, #0f766e)"
    assert button.style.text_color == "var(--jp-ui-inverse-font-color1, #ffffff)"
