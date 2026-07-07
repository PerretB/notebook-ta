"""Tests for notebook_ta.bench.models."""

from __future__ import annotations

from notebook_ta.bench.models import (
    DEFAULT_TAG_COLOR,
    DEFAULT_TAG_COLORS,
    BenchProject,
    BenchSettings,
    ExecutionRecord,
    InputSnapshot,
    ModelUnderTest,
    PromptVersion,
    StudentSolution,
)
from notebook_ta.config.models import LLMConfig


def make_settings() -> BenchSettings:
    return BenchSettings(
        internal_model=LLMConfig(
            provider="ollama", model="llama3.2:3b", base_url="http://localhost:11434"
        )
    )


def make_snapshot(statement: str = "stmt", code: str = "code") -> InputSnapshot:
    return InputSnapshot(
        exercise_statement=statement,
        tests_serialized="[]",
        student_code=code,
        exercise_hash="ex-hash",
        student_hash="student-hash",
        combined_hash="combined-hash",
    )


class TestBenchProjectHelpers:
    def test_tag_colors_have_defaults_and_safe_fallback(self) -> None:
        settings = make_settings()

        assert settings.tag_colors == DEFAULT_TAG_COLORS
        assert settings.color_for_tag("custom") == DEFAULT_TAG_COLOR
        settings.tag_colors["custom"] = "not-a-color"
        assert settings.color_for_tag("custom") == DEFAULT_TAG_COLOR

    def test_next_prompt_version_id_sequence(self) -> None:
        project = BenchProject(settings=make_settings())
        assert project.next_prompt_version_id() == "V1"
        project.prompt_versions.append(
            PromptVersion(id="V1", on_success="s", on_failure="f")
        )
        assert project.next_prompt_version_id() == "V2"

    def test_solutions_for_filters_by_exercise(self) -> None:
        project = BenchProject(settings=make_settings())
        project.solutions.append(StudentSolution(exercise_id="ex1", code="a"))
        project.solutions.append(StudentSolution(exercise_id="ex2", code="b"))
        result = project.solutions_for("ex1")
        assert len(result) == 1
        assert result[0].code == "a"

    def test_setup_code_for_returns_project_value_or_empty_string(self) -> None:
        project = BenchProject(settings=make_settings())
        assert project.setup_code_for("ex1") == ""
        project.setup_code_by_exercise["ex1"] = "expected = 5"
        assert project.setup_code_for("ex1") == "expected = 5"

    def test_latest_record_returns_most_recent(self) -> None:
        project = BenchProject(settings=make_settings())
        older = ExecutionRecord(
            run_id="run1",
            exercise_id="ex1",
            solution_id="sol1",
            model_label="m1",
            prompt_version_id="V1",
            input_snapshot=make_snapshot(),
        )
        newer = ExecutionRecord(
            run_id="run2",
            exercise_id="ex1",
            solution_id="sol1",
            model_label="m1",
            prompt_version_id="V1",
            input_snapshot=make_snapshot(),
        )
        project.execution_records.extend([older, newer])
        result = project.latest_record("ex1", "sol1", "m1", "V1")
        assert result is not None
        assert result.created_at >= older.created_at

    def test_latest_record_none_when_no_match(self) -> None:
        project = BenchProject(settings=make_settings())
        assert project.latest_record("ex1", "sol1", "m1", "V1") is None

    def test_known_combinations_deduplicates(self) -> None:
        project = BenchProject(settings=make_settings())
        for _ in range(2):
            project.execution_records.append(
                ExecutionRecord(
                    run_id="run1",
                    exercise_id="ex1",
                    solution_id="sol1",
                    model_label="m1",
                    prompt_version_id="V1",
                    input_snapshot=make_snapshot(),
                )
            )
        combos = project.known_combinations("ex1", "sol1")
        assert combos == [("m1", "V1")]


class TestBenchProjectSerialization:
    def test_round_trip_json(self) -> None:
        project = BenchProject(settings=make_settings())
        project.models_under_test.append(
            ModelUnderTest(
                label="llama3.2:3b (ollama)",
                llm_config=LLMConfig(
                    provider="ollama", model="llama3.2:3b", base_url="http://localhost:11434"
                ),
            )
        )
        data = project.model_dump_json()
        restored = BenchProject.model_validate_json(data)
        assert restored.models_under_test[0].label == "llama3.2:3b (ollama)"
        assert restored.schema_version == project.schema_version

    def test_project_setup_code_round_trips_json(self) -> None:
        project = BenchProject(settings=make_settings())
        project.setup_code_by_exercise["ex1"] = "expected = 5"

        restored = BenchProject.model_validate_json(project.model_dump_json())

        assert restored.setup_code_for("ex1") == "expected = 5"

    def test_project_without_tag_colors_loads_with_defaults(self) -> None:
        project = BenchProject(settings=make_settings())
        data = project.model_dump()
        del data["settings"]["tag_colors"]

        restored = BenchProject.model_validate(data)

        assert restored.settings.tag_colors == DEFAULT_TAG_COLORS
