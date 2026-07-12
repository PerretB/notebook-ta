"""Tests for notebook display helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from IPython import display as ipydisplay

from notebook_ta.i18n import set_language, translate
from notebook_ta.notebook.display import (
    _BACKGROUND_TASKS,
    display_busy_message,
    display_hints_button,
    display_initialization,
    display_ollama_setup,
    display_test_results,
    format_llm_answer_markdown,
    format_llm_waiting_markdown,
    set_hint_buttons_busy,
)
from notebook_ta.testing.runner import TestResult as RunnerResult


@pytest.fixture(autouse=True)
def reset_display_language() -> None:
    """Keep display helper tests independent from global language state."""
    set_language("en")
    yield
    set_language("en")


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
    assert f"{translate('display_llm_answer_prefix')}: Nice work." in rendered
    assert rendered.endswith("</div>")


def test_format_llm_waiting_markdown_contains_animated_spinner() -> None:
    """The initial LLM answer block should communicate that work is in progress."""
    rendered = format_llm_waiting_markdown()

    assert "notebook-ta-spinner" in rendered
    assert "@keyframes notebook-ta-spin" in rendered
    assert 'role="status"' in rendered


def test_display_busy_message_renders_retry_guidance() -> None:
    """Busy warnings should tell users to wait instead of starting nested work."""
    with patch("notebook_ta.notebook.display.ipydisplay.display") as display_mock:
        display_busy_message()

    rendered = display_mock.call_args.args[0]
    assert isinstance(rendered, ipydisplay.Markdown)
    assert translate("display_busy") in rendered.data


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


def test_display_hints_button_shows_busy_status_locally() -> None:
    """Rejected hint requests should update the existing widget, not display elsewhere."""
    set_hint_buttons_busy(False)
    with patch("notebook_ta.notebook.display.ipydisplay.display") as display_mock:
        display_hints_button("exercise-id", callback=lambda _exercise_id: False)

    button_output = display_mock.call_args_list[1].args[0]
    button, status = button_output.children

    button.click()

    assert translate("display_hints_busy_status") in status.value
    assert display_mock.call_count == 2


async def test_display_hints_button_retains_async_callback_until_completion() -> None:
    """Async hint requests should keep their wrapper task alive until completion."""
    set_hint_buttons_busy(False)
    callback_started = asyncio.Event()
    release_callback = asyncio.Event()

    async def _callback(_exercise_id: str) -> bool:
        callback_started.set()
        await release_callback.wait()
        return True

    with patch("notebook_ta.notebook.display.ipydisplay.display") as display_mock:
        display_hints_button("exercise-id", callback=_callback)

    button, status = display_mock.call_args_list[1].args[0].children
    button.click()

    await callback_started.wait()
    assert len(_BACKGROUND_TASKS) == 1
    assert button.disabled is True
    assert button.description == translate("display_hints_fetching")

    release_callback.set()
    await asyncio.gather(*list(_BACKGROUND_TASKS))

    assert len(_BACKGROUND_TASKS) == 0
    assert button.disabled is False
    assert button.description == translate("display_hints_button")
    assert status.value == ""


def test_hint_buttons_can_be_disabled_and_restored_globally() -> None:
    """All registered hint buttons should reflect the notebook-ta busy state."""
    set_hint_buttons_busy(False)
    with patch("notebook_ta.notebook.display.ipydisplay.display") as display_mock:
        display_hints_button("ex1", callback=lambda _exercise_id: None)
        display_hints_button("ex2", callback=lambda _exercise_id: None)

    first_button = display_mock.call_args_list[1].args[0].children[0]
    second_button = display_mock.call_args_list[3].args[0].children[0]

    set_hint_buttons_busy(True)

    assert first_button.disabled is True
    assert second_button.disabled is True
    assert first_button.description == translate("display_hints_busy_button")
    assert second_button.description == translate("display_hints_busy_button")

    set_hint_buttons_busy(False)

    assert first_button.disabled is False
    assert second_button.disabled is False
    assert first_button.description == translate("display_hints_button")
    assert second_button.description == translate("display_hints_button")


def test_busy_hint_button_click_does_not_call_callback() -> None:
    """A click event that arrives while globally busy should be ignored locally."""
    callback_called = False

    def _callback(_exercise_id: str) -> None:
        nonlocal callback_called
        callback_called = True

    set_hint_buttons_busy(False)
    with patch("notebook_ta.notebook.display.ipydisplay.display") as display_mock:
        display_hints_button("exercise-id", callback=_callback)

    button = display_mock.call_args_list[1].args[0].children[0]
    set_hint_buttons_busy(True)

    button.click()

    assert callback_called is False
    assert button.disabled is True
    assert button.description == translate("display_hints_busy_button")

    set_hint_buttons_busy(False)


def test_display_busy_message_uses_configured_language() -> None:
    """Notebook warnings should use the active configured language."""
    set_language("fr")

    with patch("notebook_ta.notebook.display.ipydisplay.display") as display_mock:
        display_busy_message()

    rendered = display_mock.call_args.args[0]
    assert isinstance(rendered, ipydisplay.Markdown)
    assert translate("display_busy", language="fr") in rendered.data


def test_display_ollama_setup_updates_spinner_and_escapes_detail() -> None:
    """Ollama setup should show activity safely and settle on a final status."""
    with patch("notebook_ta.notebook.display.ipydisplay.display") as display_mock:
        update = display_ollama_setup()

    status = display_mock.call_args.args[0]
    assert "notebook-ta-spinner" in status.value
    update("pulling_model", "pulling <manifest>")
    assert "&lt;manifest&gt;" in status.value
    assert "notebook-ta-spinner" in status.value

    update("ready")
    assert translate("ollama_setup_ready") in status.value
    assert "notebook-ta-spinner" not in status.value


def test_initialization_display_uses_llm_answer_style_and_one_display_handle() -> None:
    """Initialization should reuse the LLM-answer Markdown presentation in place."""
    with patch("notebook_ta.notebook.display.ipydisplay.display") as display_mock:
        initialization = display_initialization()

    initial = display_mock.call_args.args[0]
    assert isinstance(initial, ipydisplay.Markdown)
    assert display_mock.call_args.kwargs["display_id"] is True
    assert "background: rgba(20, 184, 166, 0.14)" in initial.data
    assert "border-left: 4px solid #14b8a6" in initial.data
    assert "border-radius: 6px" in initial.data
    assert "color: inherit" in initial.data

    initialization.show_hardware(16.0, "GPU <name>", 8.0, "model<1>", "Fast & local")
    initialization.update_ollama("pulling_model", "pulling <manifest>")
    initialization.show_loaded("ollama", "model<1>", 3)

    assert display_mock.return_value.update.call_count == 3
    content = display_mock.return_value.update.call_args.args[0].data
    assert translate("initialization_title") in content
    assert "GPU &lt;name&gt;" in content
    assert "model&lt;1&gt;" in content
    assert "pulling &lt;manifest&gt;" in content
    assert translate("ollama_setup_pulling_model") in content
    assert "3 exercise(s) registered" in content
