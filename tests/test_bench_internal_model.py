"""Tests for notebook_ta.bench.internal_model."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from notebook_ta.bench.internal_model import InternalModelService, build_authoring_prompt
from notebook_ta.bench.models import BenchSettings
from notebook_ta.config.models import ExerciseConfig, LLMConfig
from notebook_ta.llm.base import LLMProvider, TokenUsage


class FakeStreamingProvider(LLMProvider):
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.received_prompt: str | None = None

    @classmethod
    def from_config(cls, config: LLMConfig) -> FakeStreamingProvider:  # pragma: no cover
        return cls([])

    def is_available(self) -> bool:
        return True

    async def query(self, prompt: str) -> str:  # pragma: no cover - unused
        return "".join(self.chunks)

    async def stream(self, prompt: str):
        self.received_prompt = prompt
        for chunk in self.chunks:
            yield chunk

    def get_last_usage(self) -> TokenUsage | None:
        return None


def make_settings() -> BenchSettings:
    return BenchSettings(
        internal_model=LLMConfig(
            provider="ollama", model="llama3.2:3b", base_url="http://localhost:11434"
        )
    )


class TestBuildAuthoringPrompt:
    def test_includes_statement_and_tags(self) -> None:
        exercise = ExerciseConfig(id="ex1", statement="Write add(a, b).")
        prompt = build_authoring_prompt(exercise, ["wrong complexity"])
        assert "Write add(a, b)." in prompt
        assert "wrong complexity" in prompt

    def test_no_tags_requests_correct_solution(self) -> None:
        exercise = ExerciseConfig(id="ex1", statement="Write add(a, b).")
        prompt = build_authoring_prompt(exercise, [])
        assert "correct Python solution" in prompt

    def test_includes_optional_fields(self) -> None:
        exercise = ExerciseConfig(
            id="ex1",
            statement="Write add(a, b).",
            expected_output="5",
            additional_info="Use type hints.",
        )
        prompt = build_authoring_prompt(exercise, [])
        assert "5" in prompt
        assert "Use type hints." in prompt


class TestInternalModelService:
    @pytest.mark.asyncio
    async def test_generate_solution_streams_chunks(self) -> None:
        exercise = ExerciseConfig(id="ex1", statement="Write add(a, b).")
        provider = FakeStreamingProvider(["def add(a", ", b): return a + b"])
        service = InternalModelService(make_settings())
        with patch("notebook_ta.bench.internal_model.create_provider", return_value=provider):
            chunks = [c async for c in service.generate_solution(exercise, ["correct"])]
        assert "".join(chunks) == "def add(a, b): return a + b"
        assert "Write add(a, b)." in provider.received_prompt
        assert "correct" in provider.received_prompt
