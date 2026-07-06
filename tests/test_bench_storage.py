"""Tests for notebook_ta.bench.storage.ProjectStore."""

from __future__ import annotations

from pathlib import Path

import pytest

import notebook_ta.bench.storage as storage_module
from notebook_ta.bench.models import BenchProject, BenchProjectError, ModelUnderTest
from notebook_ta.bench.storage import ProjectStore, get_last_project_path, set_last_project_path
from notebook_ta.config.models import LLMConfig


class TestProjectStoreLoad:
    def test_load_without_path_returns_blank_project(self) -> None:
        store = ProjectStore(None)
        project = store.load()
        assert isinstance(project, BenchProject)
        assert project.solutions == []

    def test_load_missing_file_returns_blank_project(self, tmp_path: Path) -> None:
        store = ProjectStore(tmp_path / "missing.json")
        project = store.load()
        assert isinstance(project, BenchProject)

    def test_load_rejects_unsupported_schema_version(self, tmp_path: Path) -> None:
        path = tmp_path / "project.json"
        project = ProjectStore(None).load()
        project.schema_version = 999
        path.write_text(project.model_dump_json(), encoding="utf-8")
        store = ProjectStore(path)
        with pytest.raises(BenchProjectError, match="schema_version"):
            store.load()

    def test_load_rejects_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "project.json"
        path.write_text("{not valid json", encoding="utf-8")
        store = ProjectStore(path)
        with pytest.raises(BenchProjectError):
            store.load()


class TestProjectStoreSaveRoundTrip:
    def test_save_as_then_load_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "subdir" / "project.json"
        store = ProjectStore(None)
        project = store.load()
        project.models_under_test.append(
            ModelUnderTest(
                label="llama3.2:3b (ollama)",
                llm_config=LLMConfig(
                    provider="ollama", model="llama3.2:3b", base_url="http://localhost:11434"
                ),
            )
        )
        store.save_as(project, path)
        assert path.exists()

        reloaded = ProjectStore(path).load()
        assert reloaded.models_under_test[0].label == "llama3.2:3b (ollama)"

    def test_save_without_path_raises(self) -> None:
        store = ProjectStore(None)
        project = store.load()
        with pytest.raises(BenchProjectError):
            store.save(project)

    def test_save_updates_existing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "project.json"
        store = ProjectStore(path)
        project = store.load()
        store.save(project)

        project.draft_prompt_on_success = "updated"
        store.save(project)

        reloaded = ProjectStore(path).load()
        assert reloaded.draft_prompt_on_success == "updated"

    def test_save_leaves_no_temp_files_behind(self, tmp_path: Path) -> None:
        path = tmp_path / "project.json"
        store = ProjectStore(path)
        project = store.load()
        store.save(project)
        leftovers = list(tmp_path.glob(".bench-*"))
        assert leftovers == []


class TestLastProjectPath:
    def test_get_last_project_path_none_when_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(storage_module, "_LAST_PROJECT_FILE", tmp_path / "last.json")
        assert get_last_project_path() is None

    def test_set_then_get_round_trip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(storage_module, "_LAST_PROJECT_FILE", tmp_path / "sub" / "last.json")
        project_path = tmp_path / "my_project.json"
        project_path.write_text("{}", encoding="utf-8")

        set_last_project_path(project_path)

        assert get_last_project_path() == project_path

    def test_get_last_project_path_none_when_file_no_longer_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(storage_module, "_LAST_PROJECT_FILE", tmp_path / "last.json")
        missing_path = tmp_path / "gone.json"
        set_last_project_path(missing_path)

        assert get_last_project_path() is None

    def test_load_with_explicit_path_remembers_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(storage_module, "_LAST_PROJECT_FILE", tmp_path / "last.json")
        path = tmp_path / "project.json"
        ProjectStore(path).save(ProjectStore(None).load())

        ProjectStore(path).load()

        assert get_last_project_path() == path

    def test_save_as_remembers_last_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(storage_module, "_LAST_PROJECT_FILE", tmp_path / "last.json")
        path = tmp_path / "project.json"
        store = ProjectStore(None)
        project = store.load()

        store.save_as(project, path)

        assert get_last_project_path() == path
