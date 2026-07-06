"""Settings tab: project lifecycle, internal model, Python path, autosave, and tags."""

from __future__ import annotations

from collections.abc import Callable

from nicegui import events, ui

from notebook_ta.bench.models import DEFAULT_TAG_COLOR
from notebook_ta.bench.state import BenchAppState
from notebook_ta.bench.ui._helpers import tracked_on_change
from notebook_ta.bench.ui.native_dialogs import pick_path
from notebook_ta.bench.ui.tag_badges import render_tag_badge


def build(
    state: BenchAppState,
    on_tags_change: Callable[[], object] | None = None,
) -> None:
    """Render the Settings tab."""
    project = state.project

    with ui.card().classes("w-full"):
        ui.label("Project").classes("text-md font-bold")
        ui.label(str(state.store.path or "Unsaved project")).classes("text-caption")
        with ui.row().classes("items-center gap-2"):

            async def _save_as() -> None:
                path = await pick_path(
                    "save_file",
                    filetypes=[("Benchmark project", "*.json")],
                    defaultextension=".json",
                    initialfile=state.suggested_project_filename,
                )
                if not path:
                    return
                try:
                    state.save_as(path)
                except Exception as exc:
                    ui.notify(f"Could not save project: {exc}", type="negative")
                    return
                ui.navigate.reload()

            ui.button("Save As", on_click=_save_as)

            def _close() -> None:
                try:
                    state.close_project()
                except Exception as exc:
                    ui.notify(f"Could not close project: {exc}", type="warning")
                    return
                ui.navigate.reload()

            def _request_close() -> None:
                if not state.dirty:
                    _close()
                    return
                with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
                    ui.label("Close this project?").classes("text-lg font-bold")
                    ui.label(
                        "Unsaved changes will be lost. This cannot be undone."
                    ).classes("text-negative")
                    with ui.row().classes("justify-end w-full"):
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                        ui.button("Close without saving", on_click=_close).props(
                            "color=negative"
                        )
                dialog.open()

            ui.button("Close project", icon="close", on_click=_request_close).props(
                "outline color=negative"
            )

        ui.checkbox(
            "Auto-save",
            value=project.settings.autosave_enabled,
            on_change=tracked_on_change(state, project.settings, "autosave_enabled"),
        )
        ui.number(
            "Auto-save interval (s)",
            value=project.settings.autosave_interval_seconds,
            on_change=tracked_on_change(state, project.settings, "autosave_interval_seconds", int),
        )

    with ui.card().classes("w-full"):
        ui.label("Internal Model").classes("text-md font-bold")
        ui.label(
            "Used to generate draft student solutions in the Exercises tab. "
            "Not used to assess or score benchmark output."
        ).classes("text-caption")
        internal_model = project.settings.internal_model
        with ui.row().classes("items-center gap-2"):
            ui.select(
                ["ollama", "openai_compat"],
                value=internal_model.provider,
                label="Provider",
                on_change=tracked_on_change(state, internal_model, "provider"),
            )
            ui.input(
                "Model",
                value=internal_model.model,
                on_change=tracked_on_change(state, internal_model, "model"),
            )
            ui.input(
                "Base URL",
                value=internal_model.base_url,
                on_change=tracked_on_change(state, internal_model, "base_url"),
            )
            ui.input(
                "API Key",
                value=internal_model.api_key or "",
                password=True,
                on_change=tracked_on_change(
                    state, internal_model, "api_key", lambda value: value or None
                ),
            )

    with ui.card().classes("w-full"):
        ui.label("Python Path").classes("text-md font-bold")
        ui.label("Directories added to sys.path for external unit test modules.").classes(
            "text-caption"
        )
        dirs_container = ui.column()

        def _refresh_dirs() -> None:
            dirs_container.clear()
            with dirs_container:
                for index, directory in enumerate(project.settings.python_path_dirs):
                    with ui.row().classes("items-center gap-2"):
                        ui.label(directory)

                        def _remove(idx: int = index) -> None:
                            project.settings.python_path_dirs.pop(idx)
                            state.mark_dirty()
                            _refresh_dirs()

                        ui.button(icon="delete", on_click=_remove).props("flat dense")

        _refresh_dirs()

        new_dir_input = ui.input("Add directory")

        def _add_dir() -> None:
            if new_dir_input.value:
                project.settings.python_path_dirs.append(new_dir_input.value)
                state.mark_dirty()
                new_dir_input.value = ""
                _refresh_dirs()

        async def _browse_dir() -> None:
            path = await pick_path("directory")
            if path:
                project.settings.python_path_dirs.append(path)
                state.mark_dirty()
                _refresh_dirs()

        with ui.row().classes("items-center gap-2"):
            ui.button("Add", on_click=_add_dir)
            ui.button("Browse...", icon="folder_open", on_click=_browse_dir)

    with ui.card().classes("w-full"):
        ui.label("Tags").classes("text-md font-bold")
        ui.label(
            "Shared tag vocabulary offered when tagging student solutions or generating "
            "drafts with the internal model (Exercises tab)."
        ).classes("text-caption")
        tags_container = ui.column()

        def _refresh_tags() -> None:
            tags_container.clear()
            with tags_container:
                for index, tag in enumerate(project.settings.known_tags):
                    with ui.row().classes("items-center gap-2"):
                        def _change_color(
                            event: events.ColorPickEventArguments,
                            tag_name: str = tag,
                        ) -> None:
                            project.settings.tag_colors[tag_name] = event.color
                            state.mark_dirty()
                            if on_tags_change is not None:
                                on_tags_change()
                            _refresh_tags()

                        render_tag_badge(project.settings, tag)
                        picker = ui.color_picker(on_pick=_change_color).set_color(
                            project.settings.color_for_tag(tag)
                        )
                        ui.button(icon="colorize", on_click=picker.open).props(
                            "flat dense round"
                        ).tooltip(f"Change color for {tag}")

                        def _remove_tag(idx: int = index) -> None:
                            removed_tag = project.settings.known_tags.pop(idx)
                            project.settings.tag_colors.pop(removed_tag, None)
                            state.mark_dirty()
                            if on_tags_change is not None:
                                on_tags_change()
                            _refresh_tags()

                        ui.button(icon="delete", on_click=_remove_tag).props("flat dense")

        _refresh_tags()

        new_tag_input = ui.input("Add tag")

        def _add_tag() -> None:
            tag = new_tag_input.value.strip()
            if tag and tag not in project.settings.known_tags:
                project.settings.known_tags.append(tag)
                project.settings.tag_colors[tag] = DEFAULT_TAG_COLOR
                state.mark_dirty()
                if on_tags_change is not None:
                    on_tags_change()
                new_tag_input.value = ""
                _refresh_tags()

        ui.button("Add", on_click=_add_tag)
