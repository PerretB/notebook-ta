"""Tests for style-preserving exercise catalog edits."""

from __future__ import annotations

from pathlib import Path

import pytest

from notebook_ta.bench.catalog import add_exercise, set_exercise_name
from notebook_ta.config.loader import load_exercises
from notebook_ta.config.models import ConfigurationError, ExerciseConfig


def _write_catalog(path: Path) -> None:
    """Write a minimal catalog containing formatting that edits must preserve."""
    path.write_text(
        '# catalog comment\n\n[exercises.ex1]\nstatement = "Example"\n',
        encoding="utf-8",
    )


def test_name_edit_and_exercise_addition_preserve_existing_catalog_content(
    tmp_path: Path,
) -> None:
    """Catalog mutations must retain comments and produce loadable exercises."""
    path = tmp_path / "exercises.toml"
    _write_catalog(path)

    set_exercise_name(path, "ex1", "First exercise")
    add_exercise(
        path,
        ExerciseConfig(id="ex2", name="Second exercise", statement="Solve this."),
    )

    content = path.read_text(encoding="utf-8")
    assert "# catalog comment" in content
    exercises = load_exercises(path)
    assert [(exercise.id, exercise.name) for exercise in exercises] == [
        ("ex1", "First exercise"),
        ("ex2", "Second exercise"),
    ]
    assert exercises[1].statement == "Solve this."


def test_remote_catalog_is_read_only() -> None:
    """Authoring mutations must reject catalogs which cannot be written locally."""
    with pytest.raises(ConfigurationError, match="read-only"):
        set_exercise_name("https://example.test/exercises.toml", "ex1", "Name")
