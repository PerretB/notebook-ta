"""Persistence for `BenchProject`: JSON load/save with atomic writes.

Unlike `notebook_ta.config.loader`, project files are always local (no remote
loading) -- this is a local, single-user authoring tool.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from notebook_ta.bench.models import BenchProject, BenchProjectError, BenchSettings
from notebook_ta.config.models import LLMConfig
from notebook_ta.logging import get_logger

_log = get_logger("bench.storage")

CURRENT_SCHEMA_VERSION = 1

# Small, user-scoped (not project-scoped) pointer file remembering the last opened
# project, so `notebook-ta bench` with no argument can reopen it automatically.
_LAST_PROJECT_FILE = Path.home() / ".notebook_ta" / "bench_last_project.json"


def get_last_project_path() -> Path | None:
    """Return the path of the last opened benchmarking project, if any and if it still exists."""
    try:
        data = json.loads(_LAST_PROJECT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    path = data.get("last_project_path")
    if not path:
        return None
    candidate = Path(path)
    return candidate if candidate.exists() else None


def set_last_project_path(path: Path | str) -> None:
    """Remember `path` as the last opened benchmarking project (best-effort, never raises)."""
    try:
        _LAST_PROJECT_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LAST_PROJECT_FILE.write_text(
            json.dumps({"last_project_path": str(Path(path))}), encoding="utf-8"
        )
    except OSError as exc:  # pragma: no cover - best-effort convenience feature
        _log.debug("Could not remember last project path: %s", exc)


def _default_project() -> BenchProject:
    """Return a blank project with a placeholder internal model configuration."""
    return BenchProject(
        settings=BenchSettings(
            internal_model=LLMConfig(
                provider="ollama",
                model="llama3.2:3b",
                base_url="http://localhost:11434",
            )
        )
    )


class ProjectStore:
    """Loads and saves a `BenchProject` to a local JSON file."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path: Path | None = Path(path) if path else None

    def load(self) -> BenchProject:
        """Load the project from `self.path`, or return a blank project if unset/missing."""
        if self.path is None or not self.path.exists():
            _log.debug("No project file at %r; starting a new project.", str(self.path))
            return _default_project()

        _log.debug("Loading benchmarking project from %s", self.path)
        text = self.path.read_text(encoding="utf-8")
        try:
            project = BenchProject.model_validate_json(text)
        except ValidationError as exc:
            raise BenchProjectError(f"Failed to parse project file {self.path}: {exc}") from exc

        if project.schema_version != CURRENT_SCHEMA_VERSION:
            raise BenchProjectError(
                f"Unsupported project schema_version {project.schema_version!r} "
                f"(expected {CURRENT_SCHEMA_VERSION}). File: {self.path}"
            )
        set_last_project_path(self.path)
        return project

    def save(self, project: BenchProject) -> None:
        """Save `project` to `self.path`. Requires a path to have been set via `save_as()`."""
        if self.path is None:
            raise BenchProjectError("No project file path set; use save_as() first.")
        self._write(project, self.path)

    def save_as(self, project: BenchProject, path: Path | str) -> None:
        """Save `project` to a new path and remember it as the active path."""
        self.path = Path(path)
        self._write(project, self.path)
        set_last_project_path(self.path)

    @staticmethod
    def _write(project: BenchProject, path: Path) -> None:
        """Write the project JSON atomically (temp file + `os.replace`)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = project.model_dump_json(indent=2)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".bench-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
            os.replace(tmp_name, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.remove(tmp_name)
            raise
        _log.debug("Saved benchmarking project to %s", path)
