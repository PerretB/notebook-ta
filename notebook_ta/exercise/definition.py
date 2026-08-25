"""Exercise class and prompt construction logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

from notebook_ta.config.models import (
    ConfigurationError,
    ExerciseConfig,
    GlobalConfig,
    TestDefinition,
)
from notebook_ta.config.prompt_templates import PromptTemplateError

if TYPE_CHECKING:
    from notebook_ta.notebook.session import HintExchange
    from notebook_ta.testing.runner import TestResult

class Exercise:
    """Wraps an ExerciseConfig and provides prompt construction logic."""

    def __init__(self, config: ExerciseConfig, global_config: GlobalConfig) -> None:
        self._config = config
        self._global = global_config
        self._validate_prompt_overrides()

    def _validate_prompt_overrides(self) -> None:
        """Fail early when an exercise prompt override cannot be expanded."""
        prompt_config = self._global.prompts
        for field_name in ("prompt_on_success", "prompt_on_failure"):
            template = getattr(self._config, field_name)
            if template is None:
                continue
            try:
                prompt_config.expand_template(
                    template,
                    location=f"exercises.{self.id}.{field_name}",
                )
            except PromptTemplateError as exc:
                raise ConfigurationError(
                    f"Invalid prompt configuration for exercise {self.id!r}: {exc}"
                ) from exc

    @property
    def id(self) -> str:
        """Return the stable exercise identifier."""
        return self._config.id

    @property
    def statement(self) -> str:
        """Return the exercise statement.

        Raises:
            AssertionError: If called before the statement has been resolved
                (i.e. before ``notebook_ta.load()`` has completed successfully).
        """
        assert self._config.statement is not None, (
            f"Exercise {self._config.id!r}: statement must be resolved before the "
            "exercise is used. Ensure notebook_ta.load() completed without errors."
        )
        return self._config.statement

    @property
    def tests(self) -> list[TestDefinition]:
        """Return the unit test definitions configured for this exercise."""
        return self._config.tests

    @property
    def config(self) -> ExerciseConfig:
        """Return the underlying exercise configuration."""
        return self._config

    @property
    def unit_test_timeout(self) -> float:
        """Return this exercise's unit test timeout in seconds."""
        return self._config.unit_test_timeout or self._global.unit_test_timeout

    @property
    def max_student_answer_length(self) -> int:
        """Return the maximum student answer length in characters."""
        configured = self._config.max_student_answer_length
        return (
            configured
            if configured is not None
            else self._global.max_student_answer_length
        )

    @property
    def max_unit_test_output_length(self) -> int:
        """Return the cumulative unit test output limit in characters."""
        configured = self._config.max_unit_test_output_length
        return (
            configured
            if configured is not None
            else self._global.max_unit_test_output_length
        )

    @property
    def language(self) -> str:
        """Return the language code configured for user-facing notebook messages."""
        return self._global.language

    def build_prompt(
        self,
        student_code: str,
        test_results: list[TestResult] | None,
        hint_history: list[HintExchange] | None = None,
    ) -> str:
        """Assemble a structured prompt for the LLM.

        Args:
            student_code: The raw student cell body.
            test_results: Results from the test runner; None means tests are not being reported.
            hint_history: Previous hint exchanges; non-empty triggers the hints prompt.

        Returns:
            A fully assembled prompt string.
        """
        prompt_config = self._global.prompts

        # 1. Active prompt
        parts: list[str] = []
        if test_results is None or all(r.passed for r in test_results):
            template = self._config.prompt_on_success
            active_prompt = (
                prompt_config.expand_template(
                    template,
                    location=f"exercises.{self.id}.prompt_on_success",
                )
                if template
                else prompt_config.on_success
            )
        else:
            template = self._config.prompt_on_failure
            active_prompt = (
                prompt_config.expand_template(
                    template,
                    location=f"exercises.{self.id}.prompt_on_failure",
                )
                if template
                else prompt_config.on_failure
            )
        parts.append(active_prompt)
        parts.append("\n\n")

        if self._global.language.casefold() != "en":
            parts.append(
                "Answer in the language identified by the BCP 47 language code "
                f'"{self._global.language}".\n\n'
            )

        # 2. Exercise metadata block
        parts.append("## Exercise\n\n")
        parts.append(f"{self.statement}\n")

        if self._config.additional_info:
            parts.append(f"\n**Additional Information:**\n{self._config.additional_info}\n")

        # 3. Student code safety instruction and code block
        parts.append("\n## Student Code\n\n")
        parts.append(prompt_config.student_code_safety_instruction)
        parts.append(f"\n\n```python\n{student_code}\n```\n")

        # 4. Test results block (only when tests failed)
        if test_results and not all(r.passed for r in test_results):
            parts.append("\n## Unit Test Results\n\n")
            for result in test_results:
                status = "✅ PASS" if result.passed else "❌ FAIL"
                parts.append(f"- **{result.name}**: {status}")
                if result.message:
                    parts.append(f"\n  Message: {result.message}")
                parts.append("\n")

        # 5. Hint history block (only for hint requests)
        if hint_history:
            max_len = prompt_config.hint_history_length
            recent_history = (
                hint_history[-max_len:]
                if len(hint_history) > max_len
                else hint_history
            )
            parts.append("\n## Previous Hint Exchanges\n\n")
            for i, exchange in enumerate(recent_history, 1):
                parts.append(f"### Exchange {i}\n\n")
                parts.append(
                    f"**Student Code at that time:**\n```python\n"
                    f"{exchange.student_code}\n```\n\n"
                )
                parts.append(f"**Your previous hint:**\n{exchange.hint_response}\n\n")

        return "".join(parts)
