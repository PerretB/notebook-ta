"""Tests for configuration loading and validation."""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from notebook_ta.config.loader import load_exercises, load_global
from notebook_ta.config.models import (
    ConfigurationError,
    GlobalConfig,
    TestDefinition,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GLOBAL_TOML_CONTENT = textwrap.dedent("""\
    unit_test_timeout = 2.5

    [llm]
    provider = "ollama"
    model = "llama3.2:3b"
    base_url = "http://localhost:11434"
    timeout = 60
    streaming = true

    [[llm.available_models]]
    name = "llama3.2:1b"
    description = "Small model"
    min_ram_gb = 4.0
    min_vram_gb = 0.0

    [[llm.available_models]]
    name = "llama3.2:3b"
    description = "Medium model"
    min_ram_gb = 8.0
    min_vram_gb = 0.0

    [prompts]
    on_success = "Great job!"
    on_failure = "Try again."
    on_no_llm = "LLM unavailable."
    hint_history_length = 3
""")

EXERCISES_TOML_CONTENT = textwrap.dedent("""\
    [exercises.ex1]
    statement = "Write an add function."
    unit_test_timeout = 1.5

    [[exercises.ex1.tests]]
    name = "Test add(2,3)"
    code = '''
    def test_add(add):
        return add(2, 3) == 5, "Expected 5"
    '''

    [exercises.ex2]
    statement = "Write a multiply function."

    [[exercises.ex2.tests]]
    name = "Test multiply"
    module = "some.module"
    function = "test_multiply"
""")


@pytest.fixture()
def global_config_file(tmp_path: Path) -> Path:
    p = tmp_path / "global_config.toml"
    p.write_text(GLOBAL_TOML_CONTENT, encoding="utf-8")
    return p


@pytest.fixture()
def exercises_file(tmp_path: Path) -> Path:
    p = tmp_path / "exercises.toml"
    p.write_text(EXERCISES_TOML_CONTENT, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# GlobalConfig loading
# ---------------------------------------------------------------------------

class TestLoadGlobal:
    def test_loads_valid_config(self, global_config_file: Path) -> None:
        cfg = load_global(global_config_file)
        assert isinstance(cfg, GlobalConfig)
        assert cfg.llm.provider == "ollama"
        assert cfg.llm.model == "llama3.2:3b"
        assert cfg.llm.timeout == 60
        assert cfg.llm.streaming is True
        assert cfg.unit_test_timeout == 2.5
        assert cfg.language == "en"
        assert len(cfg.llm.available_models) == 2
        assert cfg.prompts.on_success == "Great job!"
        assert cfg.prompts.hint_history_length == 3

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError, match="not found"):
            load_global(tmp_path / "nonexistent.toml")

    def test_invalid_toml_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.toml"
        bad.write_text("this is not toml [[[[", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="parse"):
            load_global(bad)

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        # Missing [prompts]
        content = "[llm]\nmodel = 'x'\nbase_url = 'http://x'\nprovider = 'ollama'\n"
        f = tmp_path / "missing_prompts.toml"
        f.write_text(content, encoding="utf-8")
        with pytest.raises(ConfigurationError):
            load_global(f)


# ---------------------------------------------------------------------------
# ExerciseConfig loading
# ---------------------------------------------------------------------------

class TestLoadExercises:
    def test_loads_valid_exercises(self, exercises_file: Path) -> None:
        exercises = load_exercises(exercises_file)
        assert len(exercises) == 2
        ids = [e.id for e in exercises]
        assert "ex1" in ids
        assert "ex2" in ids

    def test_ex1_has_inline_test(self, exercises_file: Path) -> None:
        exercises = load_exercises(exercises_file)
        ex1 = next(e for e in exercises if e.id == "ex1")
        assert ex1.statement == "Write an add function."
        assert ex1.unit_test_timeout == 1.5
        assert len(ex1.tests) == 1
        assert ex1.tests[0].code is not None
        assert ex1.tests[0].module is None

    def test_ex2_has_external_test(self, exercises_file: Path) -> None:
        exercises = load_exercises(exercises_file)
        ex2 = next(e for e in exercises if e.id == "ex2")
        assert ex2.tests[0].module == "some.module"
        assert ex2.tests[0].function == "test_multiply"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError, match="not found"):
            load_exercises(tmp_path / "nonexistent.toml")

    def test_no_exercises_section_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.toml"
        f.write_text("", encoding="utf-8")
        result = load_exercises(f)
        assert result == []

    def test_exercise_without_statement_loads_with_none(self, tmp_path: Path) -> None:
        """statement is optional; ExerciseConfig.statement should be None when absent."""
        content = "[exercises.ex_no_stmt]\n"
        f = tmp_path / "no_stmt.toml"
        f.write_text(content, encoding="utf-8")
        result = load_exercises(f)
        assert len(result) == 1
        assert result[0].id == "ex_no_stmt"
        assert result[0].statement is None

    def test_global_unit_test_timeout_defaults_to_five_seconds(self, tmp_path: Path) -> None:
        content = textwrap.dedent("""\
            [llm]
            provider = "ollama"
            model = "llama3.2:3b"
            base_url = "http://localhost:11434"

            [prompts]
            on_success = "Great job!"
            on_failure = "Try again."
            on_no_llm = "LLM unavailable."
        """)
        f = tmp_path / "default_timeout.toml"
        f.write_text(content, encoding="utf-8")

        cfg = load_global(f)

        assert cfg.unit_test_timeout == 5.0

    def test_global_language_defaults_to_english(self, tmp_path: Path) -> None:
        content = textwrap.dedent("""\
            [llm]
            provider = "ollama"
            model = "llama3.2:3b"
            base_url = "http://localhost:11434"

            [prompts]
            on_success = "Great job!"
            on_failure = "Try again."
            on_no_llm = "LLM unavailable."
        """)
        f = tmp_path / "default_language.toml"
        f.write_text(content, encoding="utf-8")

        cfg = load_global(f)

        assert cfg.language == "en"

    def test_unsupported_global_language_warns_and_falls_back(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        content = textwrap.dedent("""\
            language = "zz"

            [llm]
            provider = "ollama"
            model = "llama3.2:3b"
            base_url = "http://localhost:11434"

            [prompts]
            on_success = "Great job!"
            on_failure = "Try again."
            on_no_llm = "LLM unavailable."
        """)
        f = tmp_path / "unsupported_language.toml"
        f.write_text(content, encoding="utf-8")

        caplog.set_level(logging.WARNING, logger="notebook_ta.i18n")
        cfg = load_global(f)

        assert cfg.language == "en"
        assert "Unsupported language 'zz' requested" in caplog.text


# ---------------------------------------------------------------------------
# TestDefinition model validation
# ---------------------------------------------------------------------------

class TestTestDefinitionValidation:
    def test_inline_code_valid(self) -> None:
        td = TestDefinition(name="t", code="def f(): return True")
        assert td.code is not None

    def test_external_valid(self) -> None:
        td = TestDefinition(name="t", module="my.module", function="my_func")
        assert td.module == "my.module"

    def test_both_raises(self) -> None:
        with pytest.raises(ValidationError):
            TestDefinition(name="t", code="def f(): pass", module="m", function="f")

    def test_neither_raises(self) -> None:
        with pytest.raises(ValidationError):
            TestDefinition(name="t")

    def test_module_without_function_raises(self) -> None:
        with pytest.raises(ValidationError):
            TestDefinition(name="t", module="my.module")


# ---------------------------------------------------------------------------
# Remote loading (mocked via pytest-httpx)
# ---------------------------------------------------------------------------

class TestRemoteLoading:
    def test_load_global_from_url(self, httpx_mock, tmp_path: Path) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://example.com/global.toml",
            text=GLOBAL_TOML_CONTENT,
        )
        cfg = load_global("https://example.com/global.toml")
        assert isinstance(cfg, GlobalConfig)

    def test_load_exercises_from_url(self, httpx_mock, tmp_path: Path) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://example.com/exercises.toml",
            text=EXERCISES_TOML_CONTENT,
        )
        exercises = load_exercises("https://example.com/exercises.toml")
        assert len(exercises) == 2

    def test_http_error_raises(self, httpx_mock) -> None:
        import httpx as _httpx

        httpx_mock.add_exception(
            _httpx.ConnectError("connection refused"),
            url="https://example.com/bad.toml",
        )
        with pytest.raises(ConfigurationError, match="Failed to fetch"):
            load_global("https://example.com/bad.toml")
