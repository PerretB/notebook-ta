"""Tests for the CLI scaffold generator."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from notebook_ta.cli.scaffold import cli


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EXERCISES_TOML = textwrap.dedent("""\
    [exercises.ex1]
    statement = "Write an add function."
    expected_output = "5"

    [[exercises.ex1.tests]]
    name = "Test add"
    code = "def test_add(add): return add(2,3) == 5"

    [exercises.ex2]
    statement = "Write a multiply function."

    [[exercises.ex2.tests]]
    name = "Test multiply"
    code = "def test_mul(mul): return mul(2,3) == 6"
""")


@pytest.fixture()
def exercises_file(tmp_path: Path) -> Path:
    p = tmp_path / "exercises.toml"
    p.write_text(EXERCISES_TOML, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# create-notebook command
# ---------------------------------------------------------------------------

class TestCreateNotebook:
    def test_notebook_created(self, exercises_file: Path, tmp_path: Path) -> None:
        runner = CliRunner()
        output_path = tmp_path / "out.ipynb"
        result = runner.invoke(cli, ["create-notebook", str(exercises_file), "--output", str(output_path)])
        assert result.exit_code == 0, result.output
        assert output_path.exists()

    def test_notebook_is_valid_json(self, exercises_file: Path, tmp_path: Path) -> None:
        runner = CliRunner()
        output_path = tmp_path / "out.ipynb"
        runner.invoke(cli, ["create-notebook", str(exercises_file), "--output", str(output_path)])
        nb = json.loads(output_path.read_text(encoding="utf-8"))
        assert "cells" in nb

    @staticmethod
    def _cell_source(cell) -> str:
        src = cell["source"]
        return "".join(src) if isinstance(src, list) else src

    def test_notebook_has_setup_cell_first(self, exercises_file: Path, tmp_path: Path) -> None:
        runner = CliRunner()
        output_path = tmp_path / "out.ipynb"
        runner.invoke(cli, ["create-notebook", str(exercises_file), "--output", str(output_path)])
        nb = json.loads(output_path.read_text(encoding="utf-8"))
        first_cell = nb["cells"][0]
        source = self._cell_source(first_cell)
        assert first_cell["cell_type"] == "code"
        assert "notebook_ta" in source
        assert "notebook_ta.load" in source

    def test_notebook_has_markdown_and_code_per_exercise(self, exercises_file: Path, tmp_path: Path) -> None:
        runner = CliRunner()
        output_path = tmp_path / "out.ipynb"
        runner.invoke(cli, ["create-notebook", str(exercises_file), "--output", str(output_path)])
        nb = json.loads(output_path.read_text(encoding="utf-8"))
        # 1 setup + 2 exercises * 2 cells = 5
        assert len(nb["cells"]) == 5

    def test_exercise_code_cells_have_magic(self, exercises_file: Path, tmp_path: Path) -> None:
        runner = CliRunner()
        output_path = tmp_path / "out.ipynb"
        runner.invoke(cli, ["create-notebook", str(exercises_file), "--output", str(output_path)])
        nb = json.loads(output_path.read_text(encoding="utf-8"))
        code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
        # Skip the setup cell
        for cell in code_cells[1:]:
            source = self._cell_source(cell)
            assert "%%notebook_ta" in source

    def test_exercise_markdown_contains_statement(self, exercises_file: Path, tmp_path: Path) -> None:
        runner = CliRunner()
        output_path = tmp_path / "out.ipynb"
        runner.invoke(cli, ["create-notebook", str(exercises_file), "--output", str(output_path)])
        nb = json.loads(output_path.read_text(encoding="utf-8"))
        md_cells = [c for c in nb["cells"] if c["cell_type"] == "markdown"]
        all_md = " ".join(self._cell_source(c) for c in md_cells)
        assert "Write an add function." in all_md
        assert "Write a multiply function." in all_md

    def test_global_config_written_into_setup_cell(self, exercises_file: Path, tmp_path: Path) -> None:
        runner = CliRunner()
        output_path = tmp_path / "out.ipynb"
        result = runner.invoke(
            cli,
            [
                "create-notebook",
                str(exercises_file),
                "--global-config",
                "my_config.toml",
                "--output",
                str(output_path),
            ],
        )
        assert result.exit_code == 0
        nb = json.loads(output_path.read_text(encoding="utf-8"))
        setup_source = self._cell_source(nb["cells"][0])
        assert "my_config.toml" in setup_source

    def test_output_file_not_specified_defaults_to_notebook(
        self, exercises_file: Path, tmp_path: Path
    ) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["create-notebook", str(exercises_file)])
            assert result.exit_code == 0
            assert Path("notebook.ipynb").exists()
