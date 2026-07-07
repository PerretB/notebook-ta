"""Pydantic v2 configuration models for notebook-ta."""

from __future__ import annotations

from pydantic import BaseModel, model_validator


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
    api_key: str | None = None
    timeout: int = 120
    temperature: float = 0.7
    streaming: bool = True
    available_models: list[ModelSpec] = []


class PromptConfig(BaseModel):
    """Default prompt strings used by the teaching assistant."""

    on_success: str
    on_failure: str
    on_no_llm: str
    hint_history_length: int = 3


class TestDefinition(BaseModel):
    """Defines a single unit test for an exercise."""

    name: str
    code: str | None = None
    module: str | None = None
    function: str | None = None

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
        return self


class ExerciseConfig(BaseModel):
    """Configuration for a single exercise."""

    id: str
    name: str | None = None
    statement: str | None = None
    additional_info: str | None = None
    prompt_on_success: str | None = None
    prompt_on_failure: str | None = None
    tests: list[TestDefinition] = []


class GlobalConfig(BaseModel):
    """Top-level global configuration combining LLM and prompt settings."""

    llm: LLMConfig
    prompts: PromptConfig


class ConfigurationError(Exception):
    """Raised when configuration loading or validation fails."""
