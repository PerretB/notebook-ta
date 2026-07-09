"""Tests for the `notebook-ta bench` CLI command."""

from __future__ import annotations

import sys
from unittest.mock import patch

from click.testing import CliRunner

from notebook_ta.bench.cli import cli


class TestBenchCLI:
    def test_bench_launches_ui_with_project_file(self, tmp_path) -> None:
        project_file = str(tmp_path / "project.json")
        runner = CliRunner()
        with patch("notebook_ta.bench.app.main") as mock_main:
            result = runner.invoke(cli, ["bench", project_file])
        assert result.exit_code == 0
        mock_main.assert_called_once_with(project_file)

    def test_bench_with_no_argument_passes_none(self) -> None:
        runner = CliRunner()
        with patch("notebook_ta.bench.app.main") as mock_main:
            result = runner.invoke(cli, ["bench"])
        assert result.exit_code == 0
        mock_main.assert_called_once_with(None)

    def test_bench_reports_friendly_error_when_nicegui_missing(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "notebook_ta.bench.app", None)
        runner = CliRunner()
        result = runner.invoke(cli, ["bench"])
        assert result.exit_code != 0
        assert "bench" in result.output
        assert "extra" in result.output

    def test_only_bench_command_is_registered(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "bench" in result.output
        assert "create-notebook" not in result.output
        assert "setup" not in result.output
