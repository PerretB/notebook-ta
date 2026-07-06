"""Small shared helpers for wiring NiceGUI element changes back into BenchAppState."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from notebook_ta.bench.state import BenchAppState


def tracked_on_change(
    state: BenchAppState, obj: Any, attr: str, cast: Callable[[Any], Any] = lambda v: v
) -> Callable[[Any], None]:
    """Return an `on_change` handler that sets `obj.attr` and marks the project dirty."""

    def handler(event: Any) -> None:
        setattr(obj, attr, cast(event.value))
        state.mark_dirty()

    return handler
