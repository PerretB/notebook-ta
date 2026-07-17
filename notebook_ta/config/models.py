"""Pydantic v2 configuration models for notebook-ta."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Annotated, ClassVar, Literal, TypeAlias

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    model_validator,
)

NonEmptyString: TypeAlias = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]


def _validate_http_url(value: str) -> str:
    """Return *value* when it is an absolute HTTP(S) URL."""
    try:
        TypeAdapter(AnyHttpUrl).validate_python(value)
    except ValidationError as exc:
        raise ValueError("must be an absolute http:// or https:// URL") from exc
    return value


HttpUrlString: TypeAlias = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
    AfterValidator(_validate_http_url),
]


class _StrictConfigModel(BaseModel):
    """Base class for configuration tables that reject undeclared fields."""

    model_config = ConfigDict(extra="forbid")


class ModelSpec(_StrictConfigModel):
    """Describes a single LLM model option and its hardware requirements."""

    name: NonEmptyString
    description: NonEmptyString
    min_ram_gb: float = Field(ge=0)
    min_vram_gb: float = Field(default=0.0, ge=0)


class LLMConfig(_StrictConfigModel):
    """LLM provider configuration."""

    provider: Literal["ollama", "openai_compat"] = "ollama"
    model: NonEmptyString
    base_url: HttpUrlString
    api_key_env: NonEmptyString | None = None
    timeout: int = Field(default=180, gt=0)
    temperature: float = Field(default=0.7, ge=0, le=2)
    streaming: bool = True
    available_models: list[ModelSpec] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def reject_literal_api_key(cls, data: object) -> object:
        """Reject plaintext API keys; configurations must reference an environment variable."""
        if isinstance(data, Mapping) and "api_key" in data:
            raise ValueError(
                "api_key is not supported; set api_key_env to an environment variable name"
            )
        return data

    @model_validator(mode="after")
    def validate_auto_model_candidates(self) -> LLMConfig:
        """Require at least one hardware candidate when automatic selection is enabled."""
        if self.model == "auto" and not self.available_models:
            raise ValueError("model='auto' requires at least one available_models entry")
        return self

    @property
    def api_key(self) -> str | None:
        """Resolve the configured API-key environment variable without persisting its value."""
        return os.environ.get(self.api_key_env) if self.api_key_env else None


class PromptConfig(_StrictConfigModel):
    """Default prompt strings used by the teaching assistant."""

    on_success: str
    on_failure: str
    on_no_llm: str
    hint_history_length: int = Field(default=3, ge=0)


class TestDefinition(_StrictConfigModel):
    """Defines a single unit test for an exercise."""

    __test__: ClassVar[bool] = False

    name: NonEmptyString
    code: str | None = None
    module: NonEmptyString | None = None
    function: NonEmptyString | None = None
    student_symbols: list[NonEmptyString] | None = None
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


class ExerciseConfig(_StrictConfigModel):
    """Configuration for a single exercise."""

    id: NonEmptyString
    name: NonEmptyString | None = None
    statement: str | None = None
    additional_info: str | None = None
    prompt_on_success: str | None = None
    prompt_on_failure: str | None = None
    unit_test_timeout: float | None = Field(default=None, gt=0)
    tests: list[TestDefinition] = Field(default_factory=list)


class GlobalConfig(_StrictConfigModel):
    """Top-level global configuration combining LLM and prompt settings."""

    llm: LLMConfig
    prompts: PromptConfig
    unit_test_timeout: float = Field(default=5.0, gt=0)
    language: str = "en"


class ConfigurationError(Exception):
    """Raised when configuration loading or validation fails."""
