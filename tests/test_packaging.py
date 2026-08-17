"""Tests for install-time dependency boundaries."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_benchmark_ui_dependencies_are_optional() -> None:
    """Keep the heavy instructor UI stack out of the student installation."""
    project_path = Path(__file__).parents[1] / "pyproject.toml"
    project = tomllib.loads(project_path.read_text(encoding="utf-8"))["project"]

    required_names = {requirement.split(">=")[0] for requirement in project["dependencies"]}
    bench_names = {
        requirement.split(">=")[0]
        for requirement in project["optional-dependencies"]["bench"]
    }

    assert {"nicegui", "tomlkit"}.isdisjoint(required_names)
    assert bench_names == {"nicegui", "tomlkit"}
