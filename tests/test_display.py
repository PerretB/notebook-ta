"""Tests for notebook display helpers."""

from __future__ import annotations

from unittest.mock import patch

from IPython import display as ipydisplay

from notebook_ta.notebook.display import display_test_results, format_llm_answer_markdown
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
