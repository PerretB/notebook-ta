"""Welcome dialog for opening or creating benchmarking projects."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from notebook_ta.bench.state import BenchAppState
from notebook_ta.bench.ui.native_dialogs import pick_path


def build(state: BenchAppState) -> None:
    """Show the persistent project chooser when no project is currently open."""
    if state.project_open:
        return

    with ui.dialog().props("persistent") as dialog, ui.card().classes("w-full max-w-3xl"):
        ui.label("Welcome to Notebook-TA Benchmarking").classes("text-2xl font-bold")
        ui.label("Open a recent project or create a new benchmark project.").classes(
            "text-grey-7"
        )

        recent_path = state.recent_project_path
        with ui.card().classes("w-full"):
            ui.label("Open a project").classes("text-lg font-bold")
            if recent_path is not None and recent_path.exists():
                ui.label(str(recent_path)).classes("text-caption text-grey-7")

                def _open_recent() -> None:
                    _load_project(state, recent_path)

                ui.button(f"Open {recent_path.name}", on_click=_open_recent).props(
                    "color=primary"
                )
            else:
                ui.label("No recent project is available.").classes("text-caption")

            async def _browse_existing() -> None:
                path = await pick_path(
                    "open_file", filetypes=[("Benchmark project", "*.json")]
                )
                if path:
                    _load_project(state, Path(path))

            ui.button("Open another project...", icon="folder_open", on_click=_browse_existing)

        with ui.card().classes("w-full"):
            ui.label("Create a new project").classes("text-lg font-bold")
            name_input = ui.input("Project name", value="benchmark-project").classes("w-full")
            ui.label(
                "The project name becomes the suggested JSON filename when you first save."
            ).classes("text-caption text-grey-7")
            with ui.row().classes("w-full items-center gap-2"):
                catalog_input = ui.input("Exercises TOML file").classes("grow")

                async def _browse_catalog() -> None:
                    path = await pick_path(
                        "open_file", filetypes=[("TOML exercise catalogs", "*.toml")]
                    )
                    if path:
                        catalog_input.value = path

                ui.button(
                    "Browse...", icon="folder_open", on_click=_browse_catalog
                ).props("flat dense").tooltip("Choose exercises TOML")

            def _create() -> None:
                if not catalog_input.value:
                    ui.notify("Choose an exercises TOML file.", type="warning")
                    return
                try:
                    state.create_project(name_input.value or "", catalog_input.value)
                except Exception as exc:
                    ui.notify(f"Could not create project: {exc}", type="negative")
                    return
                ui.navigate.reload()

            ui.button("Create project", icon="add", on_click=_create).props("color=primary")

    dialog.open()


def _load_project(state: BenchAppState, path: Path) -> None:
    """Load ``path`` and refresh the page, reporting validation errors in the UI."""
    try:
        state.load_from(path)
    except Exception as exc:
        ui.notify(f"Could not open project: {exc}", type="negative")
        return
    ui.navigate.reload()
