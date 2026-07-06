"""Exercise registry for notebook-ta."""

from __future__ import annotations

from notebook_ta.exercise.definition import Exercise
from notebook_ta.logging import get_logger

_log = get_logger("exercise")


class ExerciseNotFoundError(KeyError):
    """Raised when a requested exercise ID is not found in the registry."""


class ExerciseRegistry:
    """A dict-backed registry of Exercise instances."""

    def __init__(self) -> None:
        self._exercises: dict[str, Exercise] = {}

    def register(self, exercise: Exercise) -> None:
        """Register an exercise, replacing any existing entry with the same ID."""
        _log.debug("Registered exercise %r", exercise.id)
        self._exercises[exercise.id] = exercise

    def get(self, exercise_id: str) -> Exercise:
        """Return the Exercise with the given ID.

        Raises:
            ExerciseNotFoundError: If the ID is not found.
        """
        try:
            exercise = self._exercises[exercise_id]
        except KeyError:
            _log.warning(
                "Exercise %r not found in registry (available: %s)",
                exercise_id,
                list(self._exercises),
            )
            raise ExerciseNotFoundError(
                f"Exercise {exercise_id!r} not found in registry. "
                f"Available: {list(self._exercises)}"
            ) from None
        _log.debug("Retrieved exercise %r", exercise_id)
        return exercise

    def all(self) -> list[Exercise]:
        """Return all registered exercises in registration order."""
        return list(self._exercises.values())
