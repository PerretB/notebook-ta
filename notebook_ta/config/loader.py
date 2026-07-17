"""TOML configuration loading from local paths and remote URLs."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from notebook_ta.config.models import (
    ConfigurationError,
    ExerciseConfig,
    GlobalConfig,
)
from notebook_ta.i18n import resolve_language
from notebook_ta.logging import get_logger

_log = get_logger("config")


def _read_toml(path: str | Path) -> dict[str, Any]:
    """Read and parse a TOML file from a local path or https:// URL."""
    source = str(path)
    if source.startswith("https://"):
        _log.debug("Fetching remote TOML from %s", source)
        try:
            response = httpx.get(source, follow_redirects=True)
            response.raise_for_status()
            return tomllib.loads(response.text)
        except httpx.HTTPError as exc:
            raise ConfigurationError(
                f"Failed to fetch remote config from {source!r}: {exc}"
            ) from exc
    else:
        local_path = Path(path)
        if not local_path.exists():
            raise ConfigurationError(f"Configuration file not found: {local_path}")
        _log.debug("Loading local TOML from %s", local_path)
        try:
            with open(local_path, "rb") as fh:
                return tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationError(f"Failed to parse TOML file {local_path}: {exc}") from exc


def load_global(path: str | Path) -> GlobalConfig:
    """Load and validate global configuration from a TOML file or URL.

    Args:
        path: Local filesystem path or https:// URL to the global config TOML.

    Returns:
        Validated GlobalConfig instance.

    Raises:
        ConfigurationError: On I/O, parse, or validation failure.
    """
    _log.debug("Loading global config from %r", str(path))
    data = _read_toml(path)
    try:
        cfg = GlobalConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigurationError(
            f"Invalid global configuration in {path!r}:\n{exc}"
        ) from exc
    cfg = cfg.model_copy(update={"language": resolve_language(cfg.language)})
    _log.debug("Global config loaded: provider=%r, model=%r", cfg.llm.provider, cfg.llm.model)
    return cfg


def load_exercises(path: str | Path) -> list[ExerciseConfig]:
    """Load and validate exercise configurations from a TOML file or URL.

    The TOML file must contain an ``[exercises]`` table where each key is an
    exercise id and its value is the exercise configuration dict.

    Args:
        path: Local filesystem path or https:// URL to the exercises TOML.

    Returns:
        List of validated ExerciseConfig instances.

    Raises:
        ConfigurationError: On I/O, parse, or validation failure.
    """
    data = _read_toml(path)
    unexpected_tables = sorted(set(data) - {"exercises"})
    if unexpected_tables:
        names = ", ".join(repr(name) for name in unexpected_tables)
        raise ConfigurationError(
            f"Invalid exercises configuration in {path!r}: unexpected top-level "
            f"field(s): {names}."
        )
    exercises_raw = data.get("exercises", {})
    if not isinstance(exercises_raw, dict):
        raise ConfigurationError(
            f"Expected an [exercises] table in {path!r}, got {type(exercises_raw).__name__}."
        )

    exercises: list[ExerciseConfig] = []
    for exercise_id, exercise_data in exercises_raw.items():
        if not isinstance(exercise_data, dict):
            raise ConfigurationError(
                f"Exercise {exercise_id!r} must be a TOML table, "
                f"got {type(exercise_data).__name__}."
            )
        exercise_data = dict(exercise_data)
        if "id" in exercise_data:
            raise ConfigurationError(
                f"Invalid configuration for exercise {exercise_id!r} in {path!r}: "
                "'id' is derived from the [exercises.<id>] table name and must not "
                "be configured separately."
            )
        exercise_data["id"] = exercise_id
        try:
            exercises.append(ExerciseConfig.model_validate(exercise_data))
        except ValidationError as exc:
            raise ConfigurationError(
                f"Invalid configuration for exercise {exercise_id!r} in {path!r}:\n{exc}"
            ) from exc

    return exercises
