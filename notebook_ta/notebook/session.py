"""Per-exercise hint history management for a kernel session."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from notebook_ta.logging import get_logger

_log = get_logger("session")


@dataclass
class HintExchange:
    """A single (student_code, hint_response) exchange stored in history."""

    student_code: str
    hint_response: str


class SessionState:
    """Manages hint history for all exercises within a kernel session.

    Each exercise's history is stored in a bounded deque so that the oldest
    exchanges are dropped automatically once ``hint_history_length`` is reached.
    """

    def __init__(self, hint_history_length: int = 3) -> None:
        self._hint_history_length = hint_history_length
        self._history: dict[str, deque[HintExchange]] = {}

    def _get_deque(self, exercise_id: str) -> deque[HintExchange]:
        if exercise_id not in self._history:
            self._history[exercise_id] = deque(maxlen=self._hint_history_length)
        return self._history[exercise_id]

    def get_history(self, exercise_id: str, max_length: int) -> list[HintExchange]:
        """Return up to ``max_length`` most recent hint exchanges for an exercise."""
        dq = self._get_deque(exercise_id)
        items = list(dq)
        return items[-max_length:] if len(items) > max_length else items

    def append_hint(self, exercise_id: str, exchange: HintExchange) -> None:
        """Append a new hint exchange to the history for an exercise."""
        _log.debug("Appending hint exchange for exercise %r", exercise_id)
        self._get_deque(exercise_id).append(exchange)

    def clear(self, exercise_id: str | None = None) -> None:
        """Clear hint history for one exercise or all exercises."""
        if exercise_id is not None:
            _log.debug("Clearing hint history for exercise %r", exercise_id)
            self._history.pop(exercise_id, None)
        else:
            _log.debug("Clearing all hint history")
            self._history.clear()
