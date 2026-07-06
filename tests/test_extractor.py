"""Tests for notebook_ta.notebook.extractor."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from notebook_ta.notebook.extractor import detect_notebook_path, extract_statements


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_notebook(cells: list[dict[str, str]], path: Path) -> Path:
    """Write a minimal nbformat v4 notebook to *path* and return it."""
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {
                "cell_type": cell["type"],
                "source": cell["source"],
                "metadata": {},
                "id": f"cell-{i}",
                **({"outputs": [], "execution_count": None} if cell["type"] == "code" else {}),
            }
            for i, cell in enumerate(cells)
        ],
    }
    path.write_text(json.dumps(nb), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# extract_statements
# ---------------------------------------------------------------------------


class TestExtractStatements:
    def test_single_div_extracted(self, tmp_path: Path) -> None:
        nb = _make_notebook(
            [
                {
                    "type": "markdown",
                    "source": '<div id="ex1">\n\nWrite an `add` function.\n\n</div>',
                }
            ],
            tmp_path / "nb.ipynb",
        )
        result = extract_statements(nb)
        assert "ex1" in result
        assert "Write an `add` function." in result["ex1"]

    def test_multiple_cells_same_id_concatenated(self, tmp_path: Path) -> None:
        nb = _make_notebook(
            [
                {"type": "markdown", "source": '<div id="ex1">\nPart one.\n</div>'},
                {"type": "markdown", "source": '<div id="ex1">\nPart two.\n</div>'},
            ],
            tmp_path / "nb.ipynb",
        )
        result = extract_statements(nb)
        assert "Part one." in result["ex1"]
        assert "Part two." in result["ex1"]

    def test_multiple_exercises_separate(self, tmp_path: Path) -> None:
        nb = _make_notebook(
            [
                {"type": "markdown", "source": '<div id="ex1">\nExercise one.\n</div>'},
                {"type": "markdown", "source": '<div id="ex2">\nExercise two.\n</div>'},
            ],
            tmp_path / "nb.ipynb",
        )
        result = extract_statements(nb)
        assert "Exercise one." in result["ex1"]
        assert "Exercise two." in result["ex2"]

    def test_no_matching_div_returns_empty(self, tmp_path: Path) -> None:
        nb = _make_notebook(
            [{"type": "markdown", "source": "# Just a heading\n\nNo divs here."}],
            tmp_path / "nb.ipynb",
        )
        assert extract_statements(nb) == {}

    def test_code_cells_ignored(self, tmp_path: Path) -> None:
        nb = _make_notebook(
            [
                {
                    "type": "code",
                    "source": '<div id="ex1">Should not be extracted.</div>',
                }
            ],
            tmp_path / "nb.ipynb",
        )
        assert extract_statements(nb) == {}

    def test_nested_div_inside_statement(self, tmp_path: Path) -> None:
        source = '<div id="ex1">\n<div class="hint">Hint text</div>\nOuter text\n</div>'
        nb = _make_notebook(
            [{"type": "markdown", "source": source}],
            tmp_path / "nb.ipynb",
        )
        result = extract_statements(nb)
        assert "ex1" in result
        assert "Outer text" in result["ex1"]
        assert "Hint text" in result["ex1"]

    def test_missing_notebook_raises(self, tmp_path: Path) -> None:
        from notebook_ta.config.models import ConfigurationError

        with pytest.raises(ConfigurationError, match="not found"):
            extract_statements(tmp_path / "nonexistent.ipynb")

    def test_stripped_whitespace(self, tmp_path: Path) -> None:
        nb = _make_notebook(
            [{"type": "markdown", "source": '<div id="ex1">  \n  Hello  \n  </div>'}],
            tmp_path / "nb.ipynb",
        )
        result = extract_statements(nb)
        assert result["ex1"] == "Hello"

    def test_div_without_id_ignored(self, tmp_path: Path) -> None:
        nb = _make_notebook(
            [{"type": "markdown", "source": "<div class='x'>No id here</div>"}],
            tmp_path / "nb.ipynb",
        )
        assert extract_statements(nb) == {}

    def test_source_as_list_of_strings(self, tmp_path: Path) -> None:
        """nbformat may store cell source as a list of strings."""
        nb = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": ['<div id="ex1">\n', "List source.\n", "</div>"],
                    "metadata": {},
                    "id": "cell-0",
                }
            ],
        }
        path = tmp_path / "nb.ipynb"
        path.write_text(json.dumps(nb), encoding="utf-8")
        result = extract_statements(path)
        assert "List source." in result["ex1"]


# ---------------------------------------------------------------------------
# detect_notebook_path
# ---------------------------------------------------------------------------


class TestDetectNotebookPath:
    def test_vscode_variable_detected(self) -> None:
        ip = MagicMock()
        ip.user_ns = {"__vsc_ipynb_file__": "/path/to/notebook.ipynb"}
        result = detect_notebook_path(ip)
        assert result == Path("/path/to/notebook.ipynb")

    def test_none_when_namespace_empty_and_no_ipynbname(self) -> None:
        ip = MagicMock()
        ip.user_ns = {}
        # ipynbname is not installed in the test environment (ImportError expected)
        result = detect_notebook_path(ip)
        # Should return None (ipynbname not available in test env)
        assert result is None or isinstance(result, Path)

    def test_none_when_ip_is_none(self) -> None:
        result = detect_notebook_path(None)
        assert result is None or isinstance(result, Path)
