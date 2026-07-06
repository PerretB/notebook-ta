"""Style-preserving mutations for a local exercise TOML catalog."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

import tomlkit
from tomlkit.items import Table

from notebook_ta.config.models import ConfigurationError, ExerciseConfig


def set_exercise_name(path: str | Path, exercise_id: str, name: str) -> None:
    """Update an exercise display name while preserving unrelated TOML formatting."""
    catalog_path, document, exercises = _load_editable_catalog(path)
    exercise = exercises.get(exercise_id)
    if not isinstance(exercise, Table):
        raise ConfigurationError(f"Exercise {exercise_id!r} does not exist in {catalog_path}.")
    exercise["name"] = name
    _write_document(catalog_path, document.as_string())


def add_exercise(path: str | Path, exercise: ExerciseConfig) -> None:
    """Append a new exercise to a local TOML catalog without disturbing existing entries."""
    catalog_path, document, exercises = _load_editable_catalog(path)
    if exercise.id in exercises:
        raise ConfigurationError(f"Exercise {exercise.id!r} already exists in {catalog_path}.")

    item = tomlkit.table()
    if exercise.name:
        item.add("name", exercise.name)
    if exercise.statement:
        item.add("statement", exercise.statement)
    if exercise.expected_output:
        item.add("expected_output", exercise.expected_output)
    if exercise.additional_info:
        item.add("additional_info", exercise.additional_info)
    exercises.add(exercise.id, item)
    _write_document(catalog_path, document.as_string())


def _load_editable_catalog(path: str | Path) -> tuple[Path, tomlkit.TOMLDocument, Table]:
    """Load a local catalog and return its mutable exercises table."""
    source = str(path)
    if source.startswith(("http://", "https://")):
        raise ConfigurationError("Remote exercise catalogs are read-only.")
    catalog_path = Path(path)
    if not catalog_path.exists():
        raise ConfigurationError(f"Exercise catalog not found: {catalog_path}")
    try:
        document = tomlkit.parse(catalog_path.read_text(encoding="utf-8"))
    except (OSError, tomlkit.exceptions.ParseError) as exc:
        raise ConfigurationError(f"Could not edit exercise catalog {catalog_path}: {exc}") from exc

    exercises = document.get("exercises")
    if not isinstance(exercises, Table):
        exercises = tomlkit.table()
        document["exercises"] = exercises
    return catalog_path, document, exercises


def _write_document(path: Path, content: str) -> None:
    """Atomically replace a TOML catalog with updated content."""
    fd, temporary_name = tempfile.mkstemp(dir=str(path.parent), prefix=".exercises-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as temporary_file:
            temporary_file.write(content)
        os.replace(temporary_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(temporary_name)
        raise
