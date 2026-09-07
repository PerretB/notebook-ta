"""Tests for provider setup performed by notebook_ta.load()."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import notebook_ta
from notebook_ta import _setup_local_ollama
from notebook_ta.llm.ollama import OllamaProvider


def test_setup_local_ollama_runs_for_local_provider() -> None:
    """Local Ollama providers should be prepared during package loading."""
    provider = OllamaProvider("http://localhost:11434", "llama3.2:3b", 30)
    initialization = MagicMock()
    with patch.object(provider, "_setup_local", return_value=True) as setup:
        _setup_local_ollama(provider, initialization)

    setup.assert_called_once_with(initialization.update_ollama)


def test_setup_local_ollama_skips_remote_provider() -> None:
    """Remote Ollama providers must not be started or modified by package loading."""
    provider = OllamaProvider("http://ollama.example:11434", "llama3.2:3b", 30)
    with patch.object(provider, "_setup_local") as setup:
        _setup_local_ollama(provider)

    setup.assert_not_called()


def test_load_with_llm_disabled_skips_all_llm_setup(tmp_path: Path) -> None:
    """Disabling LLM integration must avoid provider creation and every setup operation."""
    global_config = tmp_path / "global.toml"
    global_config.write_text(
        textwrap.dedent(
            """\
            [llm]
            provider = "ollama"
            model = "auto"
            base_url = "http://localhost:11434"

            [[llm.available_models]]
            name = "llama3.2:1b"
            description = "Small model"
            min_ram_gb = 4.0
            min_vram_gb = 0.0

            [prompts]
            on_success = "Great job."
            on_failure = "Try again."
            on_no_llm = "LLM unavailable."
            """
        ),
        encoding="utf-8",
    )
    exercises_config = tmp_path / "exercises.toml"
    exercises_config.write_text(
        '[exercises.ex1]\nstatement = "Write an add function."\n',
        encoding="utf-8",
    )
    initialization = MagicMock()
    ipython = MagicMock()

    with (
        patch("notebook_ta._create_initialization_display", return_value=initialization),
        patch("notebook_ta._run_setup_wizard") as setup_wizard,
        patch("notebook_ta.create_provider") as create,
        patch("notebook_ta._setup_local_ollama") as setup_ollama,
        patch("IPython.core.getipython.get_ipython", return_value=ipython),
        patch("notebook_ta.load_ipython_extension") as register_magic,
    ):
        notebook_ta.load(global_config, exercises_config, llm_enabled=False)

    setup_wizard.assert_not_called()
    create.assert_not_called()
    setup_ollama.assert_not_called()
    register_magic.assert_called_once()
    assert register_magic.call_args.kwargs["llm_provider"] is None
    assert notebook_ta._llm_provider is None
    initialization.show_loaded_without_llm.assert_called_once_with(1)
