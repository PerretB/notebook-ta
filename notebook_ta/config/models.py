"""Pydantic v2 configuration models for notebook-ta."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import ClassVar

from pydantic import BaseModel, Field, model_validator


class ModelSpec(BaseModel):
    """Describes a single LLM model option and its hardware requirements."""

    name: str
    description: str
    min_ram_gb: float
    min_vram_gb: float = 0.0


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = "ollama"
    model: str
    base_url: str
    api_key_env: str | None = Field(default=None, min_length=1)
    timeout: int = 180
    temperature: float = 0.7
    streaming: bool = True
    available_models: list[ModelSpec] = []

    @model_validator(mode="before")
    @classmethod
    def reject_literal_api_key(cls, data: object) -> object:
        """Reject plaintext API keys; configurations must reference an environment variable."""
        if isinstance(data, Mapping) and "api_key" in data:
            raise ValueError(
                "api_key is not supported; set api_key_env to an environment variable name"
            )
        return data

    @property
    def api_key(self) -> str | None:
        """Resolve the configured API-key environment variable without persisting its value."""
        return os.environ.get(self.api_key_env) if self.api_key_env else None


class PromptConfig(BaseModel):
    """Default prompt strings used by the teaching assistant."""

    on_success: str
    on_failure: str
    on_no_llm: str
    hint_history_length: int = 3


class TestDefinition(BaseModel):
    """Defines a single unit test for an exercise."""

    __test__: ClassVar[bool] = False

    name: str
    code: str | None = None
    module: str | None = None
    function: str | None = None
    student_symbols: list[str] | None = None
    export_student_globals: bool = False

    @model_validator(mode="after")
    def validate_source(self) -> TestDefinition:
        has_inline = self.code is not None
        has_external = self.module is not None or self.function is not None
        if has_inline and has_external:
            raise ValueError(
                "TestDefinition must specify either 'code' or ('module' + 'function'), not both."
            )
        if not has_inline and not has_external:
            raise ValueError(
                "TestDefinition must specify either 'code' or ('module' + 'function')."
            )
        if has_external and (self.module is None or self.function is None):
            raise ValueError(
                "TestDefinition with external source must specify both 'module' and 'function'."
            )
        if self.student_symbols is not None and self.export_student_globals:
            raise ValueError(
                "TestDefinition cannot specify both 'student_symbols' and "
                "'export_student_globals'."
            )
        return self


class ExerciseConfig(BaseModel):
    """Configuration for a single exercise."""

    id: str
    name: str | None = None
    statement: str | None = None
    additional_info: str | None = None
    prompt_on_success: str | None = None
    prompt_on_failure: str | None = None
    unit_test_timeout: float | None = Field(default=None, gt=0)
    tests: list[TestDefinition] = []


class GlobalConfig(BaseModel):
    """Top-level global configuration combining LLM and prompt settings."""

    llm: LLMConfig
    prompts: PromptConfig
    unit_test_timeout: float = Field(default=5.0, gt=0)
    language: str = "en"


class ConfigurationError(Exception):
    """Raised when configuration loading or validation fails."""
