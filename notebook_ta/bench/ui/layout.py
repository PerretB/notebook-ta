"""Top-level page layout: tab shell, save controls, autosave timer, close guard."""

from __future__ import annotations

from nicegui import ui

from notebook_ta.bench.state import BenchAppState
from notebook_ta.bench.ui import (
    compare_tab,
    exercises_tab,
    runner_tab,
    settings_tab,
    welcome_dialog,
)
from notebook_ta.bench.ui.native_dialogs import pick_path


def build(state: BenchAppState) -> None:
    """Build the full page: top bar + tabbed main panel."""
    with ui.header().classes("items-center justify-between"):
        ui.label("Notebook-TA Benchmarking").classes("text-lg font-bold")
        with ui.row().classes("items-center gap-2"):
            status_label = ui.label()

            def _refresh_status() -> None:
                status_label.set_text("● Unsaved changes" if state.dirty else "Saved")
                ui.run_javascript(f"window.__benchDirty = {str(state.dirty).lower()};")

            ui.timer(1.0, _refresh_status)

            async def _save() -> None:
                try:
                    if state.store.path is None:
                        path = await pick_path(
                            "save_file",
                            filetypes=[("Benchmark project", "*.json")],
                            defaultextension=".json",
                            initialfile=state.suggested_project_filename,
                        )
                        if not path:
                            return
                        state.save_as(path)
                    else:
                        state.save_now()
                except Exception as exc:
                    ui.notify(f"Could not save: {exc}", type="warning")
                    return
                ui.notify("Project saved.", type="positive")

            ui.button("Save", on_click=_save)

    with ui.tabs().classes("w-full") as tabs:
        settings = ui.tab("Settings")
        exercises = ui.tab("Exercises")
        runner = ui.tab("Runner")
        compare = ui.tab("Compare")

    with ui.tab_panels(tabs, value=settings).classes("w-full"):
        with ui.tab_panel(compare):
            refresh_compare = compare_tab.build(state)
        with ui.tab_panel(exercises):
            refresh_exercises = exercises_tab.build(
                state, on_catalog_change=refresh_compare
            )

        def _refresh_tag_views() -> None:
            refresh_exercises()
            refresh_compare()

        with ui.tab_panel(settings):
            settings_tab.build(state, on_tags_change=_refresh_tag_views)
        with ui.tab_panel(runner):
            runner_tab.build(state)

    def _autosave() -> None:
        if state.project.settings.autosave_enabled and state.dirty and state.store.path is not None:
            state.save_now()

    ui.timer(max(state.project.settings.autosave_interval_seconds, 5), _autosave)

    ui.add_body_html(
        "<script>"
        "window.__benchDirty = false;"
        "window.addEventListener('beforeunload', function (e) {"
        "  if (window.__benchDirty) { e.preventDefault(); e.returnValue = ''; }"
        "});"
        "</script>"
    )
    welcome_dialog.build(state)
