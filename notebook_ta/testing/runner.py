"""Unit test runner for notebook-ta exercises."""

from __future__ import annotations

import contextlib
import importlib
import inspect
import io
import multiprocessing
import queue
import sys
import types
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

import cloudpickle  # type: ignore[import-untyped]

from notebook_ta.config.models import TestDefinition
from notebook_ta.i18n import translate

if TYPE_CHECKING:
    from notebook_ta.exercise.definition import Exercise


def _execute_test_callable(payload: bytes, result_queue: Any) -> None:
    """Run a serialized test callable in a child process and return a serialized result."""
    name, fn, args, language = cast(
        tuple[str, Callable[..., Any], dict[str, Any], str],
        cloudpickle.loads(payload),
    )
    result = TestRunner._invoke_callable(name, fn, args, language)
    result_queue.put(cloudpickle.dumps(result))


@dataclass
class TestResult:
    """Result of a single unit test execution."""

    __test__: ClassVar[bool] = False

    name: str
    passed: bool
    message: str | None = None


class TestRunner:
    """Executes the unit tests defined for an exercise."""

    def run(self, exercise: Exercise, namespace: dict[str, Any]) -> list[TestResult]:
        """Run all tests for the exercise against the given namespace.

        Args:
            exercise: The Exercise whose tests are to be run.
            namespace: The IPython user namespace containing the student's definitions.

        Returns:
            List of TestResult objects.
        """
        results: list[TestResult] = []
        for test_def in exercise.tests:
            results.append(
                self._run_one(
                    test_def,
                    namespace,
                    exercise.unit_test_timeout,
                    exercise.language,
                )
            )
        return results

    def _run_one(
        self,
        test_def: TestDefinition,
        namespace: dict[str, Any],
        timeout: float,
        language: str,
    ) -> TestResult:
        """Resolve and invoke a single test function, returning a TestResult."""
        try:
            fn = self._resolve(test_def, language)
        except Exception as exc:
            return TestResult(name=test_def.name, passed=False, message=str(exc))

        try:
            args = self._build_args(fn, namespace, language)
        except LookupError as exc:
            return TestResult(name=test_def.name, passed=False, message=str(exc))

        return self._run_with_timeout(test_def.name, fn, args, float(timeout), language)

    @staticmethod
    def _run_with_timeout(
        name: str,
        fn: Callable[..., Any],
        args: dict[str, Any],
        timeout: float,
        language: str,
    ) -> TestResult:
        """Invoke one test callable in a child process with a wall-clock timeout."""
        try:
            payload = cloudpickle.dumps((name, fn, args, language))
        except Exception as exc:
            return TestResult(
                name=name,
                passed=False,
                message=translate(
                    "runner_prepare_timeout_failed",
                    {"error": exc},
                    language=language,
                ),
            )

        ctx = multiprocessing.get_context("spawn")
        result_queue: Any = ctx.Queue()
        process = ctx.Process(target=_execute_test_callable, args=(payload, result_queue))
        sys.modules.setdefault("__main__", types.ModuleType("__main__"))
        process.start()
        process.join(timeout)

        if process.is_alive():
            process.terminate()
            process.join()
            result_queue.close()
            return TestResult(
                name=name,
                passed=False,
                message=translate("runner_timed_out", {"timeout": timeout}, language=language),
            )

        try:
            result_payload = result_queue.get_nowait()
        except queue.Empty:
            return TestResult(
                name=name,
                passed=False,
                message=translate("runner_process_no_result", language=language),
            )
        finally:
            result_queue.close()

        return cast(TestResult, cloudpickle.loads(result_payload))

    @staticmethod
    def _invoke_callable(
        name: str, fn: Callable[..., Any], args: dict[str, Any], language: str
    ) -> TestResult:
        """Invoke a resolved test callable and convert its output to a TestResult."""
        stdout_buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout_buf):
                result = fn(**args)
        except Exception as exc:
            captured = stdout_buf.getvalue()
            msg = str(exc)
            if captured:
                msg = f"{msg}\n{translate('runner_output_label', language=language)}: {captured}"
            return TestResult(name=name, passed=False, message=msg)

        captured = stdout_buf.getvalue().strip()
        return TestRunner._interpret_result(name, result, captured, language)

    @staticmethod
    def _resolve(test_def: TestDefinition, language: str) -> Callable[..., Any]:
        """Return the callable for a TestDefinition."""
        if test_def.code is not None:
            # Inline source: exec into an isolated namespace
            local_ns: dict[str, Any] = {}
            exec(test_def.code, local_ns)  # noqa: S102
            # Pick the only callable, or the one named by test_def.function
            callables: dict[str, Callable[..., Any]] = {
                k: cast(Callable[..., Any], v)
                for k, v in local_ns.items()
                if callable(v) and not k.startswith("__")
            }
            if not callables:
                raise ValueError(
                    translate(
                        "runner_inline_no_callable",
                        {"test_name": test_def.name},
                        language=language,
                    )
                )
            if test_def.function:
                if test_def.function not in callables:
                    raise ValueError(
                        translate(
                            "runner_inline_function_missing",
                            {
                                "function_name": test_def.function,
                                "test_name": test_def.name,
                            },
                            language=language,
                        )
                    )
                return callables[test_def.function]
            if len(callables) == 1:
                return next(iter(callables.values()))
            raise ValueError(
                translate(
                    "runner_inline_multiple_callables",
                    {"test_name": test_def.name, "callables": list(callables)},
                    language=language,
                )
            )
        else:
            # External module + function
            assert test_def.module is not None
            assert test_def.function is not None
            module = importlib.import_module(test_def.module)
            return cast(Callable[..., Any], getattr(module, test_def.function))

    @staticmethod
    def _build_args(
        fn: Callable[..., Any], namespace: dict[str, Any], language: str
    ) -> dict[str, Any]:
        """Build the keyword argument dict for the test function.

        If any parameter is named ``student_globals``, pass the full namespace as that argument.
        Otherwise, look up each parameter by name in the namespace.
        """
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())

        if "student_globals" in params:
            return {"student_globals": namespace}

        args: dict[str, Any] = {}
        for param in params:
            if param not in namespace:
                raise LookupError(
                    translate(
                        "runner_missing_student_name",
                        {"name": param},
                        language=language,
                    )
                )
            args[param] = namespace[param]
        return args

    @staticmethod
    def _interpret_result(
        name: str, result: object, captured_stdout: str, language: str
    ) -> TestResult:
        """Convert the raw return value + captured stdout into a TestResult."""
        if isinstance(result, bool):
            return TestResult(name=name, passed=result, message=captured_stdout or None)
        if isinstance(result, tuple) and len(result) == 2:
            passed, message = result
            full_message = str(message)
            if captured_stdout:
                full_message = (
                    f"{full_message}\n"
                    f"{translate('runner_output_label', language=language)}: {captured_stdout}"
                )
            return TestResult(name=name, passed=bool(passed), message=full_message or None)
        # Fallback: treat truthy return as pass
        passed = bool(result)
        return TestResult(name=name, passed=passed, message=captured_stdout or None)
