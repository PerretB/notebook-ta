"""NiceGUI application bootstrap for the prompt benchmarking tool."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from notebook_ta.bench.state import BenchAppState
from notebook_ta.bench.storage import ProjectStore, get_last_project_path
from notebook_ta.bench.ui import layout
from notebook_ta.logging import get_logger

_log = get_logger("bench.app")


def main(project_path: str | None = None) -> None:
    """Launch the benchmarking GUI and show its project welcome dialog.

    ``project_path`` is offered as the recent project. Otherwise the last project
    opened across previous runs is offered.
    """
    candidate = Path(project_path) if project_path else get_last_project_path()
    recent_path = candidate if candidate is not None and candidate.exists() else None
    state = BenchAppState(
        ProjectStore(None), project_open=False, recent_project_path=recent_path
    )

    @ui.page("/")
    def index() -> None:
        layout.build(state)

    ui.run(title="Notebook-TA Benchmarking", reload=False, show=True, port=0)


if __name__ in {"__main__", "__mp_main__"}:
    main()
