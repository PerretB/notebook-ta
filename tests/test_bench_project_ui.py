"""Interaction tests for benchmark project startup and Settings lifecycle controls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from nicegui import ui
from nicegui.testing import User

from notebook_ta.bench.state import BenchAppState
from notebook_ta.bench.storage import ProjectStore
from notebook_ta.bench.ui import settings_tab, welcome_dialog

pytest_plugins = ["nicegui.testing.user_plugin"]


def _write_catalog(path: Path) -> None:
    """Write a minimal valid exercise catalog for project-creation tests."""
    path.write_text('[exercises.add]\nstatement = "Add two numbers."\n', encoding="utf-8")


@pytest.mark.asyncio
@pytest.mark.nicegui_main_file("notebook_ta/bench/app.py")
async def test_welcome_dialog_creates_toml_backed_project(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The welcome dialog creates an unsaved project with a suggested filename."""
    catalog = tmp_path / "exercises.toml"
    _write_catalog(catalog)
    state = BenchAppState(ProjectStore(None), project_open=False)

    async def fake_pick_path(mode: str, **kwargs: Any) -> str:
        assert mode == "open_file"
        return str(catalog)

    monkeypatch.setattr(welcome_dialog, "pick_path", fake_pick_path)

    @ui.page("/")
    def page() -> None:
        """Render the welcome dialog under test."""
        welcome_dialog.build(state)

    await user.open("/")
    await user.should_see("Welcome to Notebook-TA Benchmarking")
    await user.should_see("Project name")
    user.find("Browse...").click()
    await user.should_see(str(catalog))
    user.find("Create project").click()

    assert state.project_open is True
    assert state.suggested_project_filename == "benchmark-project.json"
    assert list(state.exercise_registry) == ["add"]


@pytest.mark.asyncio
@pytest.mark.nicegui_main_file("notebook_ta/bench/app.py")
async def test_welcome_dialog_opens_recent_project(user: User, tmp_path: Path) -> None:
    """A remembered project is offered directly from the welcome dialog."""
    project_path = tmp_path / "recent.json"
    ProjectStore(project_path).save(ProjectStore(None).load())
    state = BenchAppState(
        ProjectStore(None), project_open=False, recent_project_path=project_path
    )

    @ui.page("/")
    def page() -> None:
        """Render the recent-project action under test."""
        welcome_dialog.build(state)

    await user.open("/")
    user.find("Open recent.json").click()

    assert state.project_open is True
    assert state.store.path == project_path


@pytest.mark.asyncio
@pytest.mark.nicegui_main_file("notebook_ta/bench/app.py")
async def test_settings_save_as_uses_picker_and_suggested_filename(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Save As delegates destination choice to the native picker."""
    destination = tmp_path / "chosen.json"
    captured: dict[str, Any] = {}

    async def fake_pick_path(mode: str, **kwargs: Any) -> str:
        captured["mode"] = mode
        captured.update(kwargs)
        return str(destination)

    monkeypatch.setattr(settings_tab, "pick_path", fake_pick_path)
    state = BenchAppState(ProjectStore(None))
    state.suggested_project_filename = "course-benchmark.json"

    @ui.page("/")
    def page() -> None:
        """Render Settings under test."""
        settings_tab.build(state)

    await user.open("/")
    await user.should_not_see("Exercise Catalog")
    user.find("Save As").click()
    await user.should_see(str(destination))

    assert destination.exists()
    assert captured["mode"] == "save_file"
    assert captured["initialfile"] == "course-benchmark.json"


@pytest.mark.asyncio
@pytest.mark.nicegui_main_file("notebook_ta/bench/app.py")
async def test_settings_close_warns_before_discarding_unsaved_changes(user: User) -> None:
    """Closing a dirty project requires explicit discard confirmation."""
    state = BenchAppState(ProjectStore(None))
    state.mark_dirty()

    @ui.page("/")
    def page() -> None:
        """Render Settings under test."""
        settings_tab.build(state)

    await user.open("/")
    user.find("Close project").click()
    await user.should_see("Unsaved changes will be lost. This cannot be undone.")
    assert state.project_open is True

    user.find("Close without saving").click()
    assert state.project_open is False


@pytest.mark.asyncio
@pytest.mark.nicegui_main_file("notebook_ta/bench/app.py")
async def test_settings_exposes_editable_color_for_each_tag(user: User) -> None:
    """Settings shows colored tag names and hides raw hex values."""
    state = BenchAppState(ProjectStore(None))

    @ui.page("/")
    def page() -> None:
        """Render Settings under test."""
        settings_tab.build(state)

    await user.open("/")
    assert len(user.find(ui.color_picker).elements) == len(
        state.project.settings.known_tags
    )
    correct_badge = next(
        badge for badge in user.find(ui.badge).elements if badge.text == "correct"
    )
    assert "#2E7D32" in str(correct_badge._style)
    assert correct_badge._props.get("color") != "primary"
    await user.should_not_see("#2E7D32")
