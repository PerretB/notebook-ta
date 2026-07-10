"""Tests for the unit test runner."""

from __future__ import annotations

import time

from notebook_ta.config.models import (
    ExerciseConfig,
    GlobalConfig,
    LLMConfig,
    PromptConfig,
    TestDefinition,
)
from notebook_ta.exercise.definition import Exercise
from notebook_ta.i18n import translate
from notebook_ta.testing.runner import TestRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_runner() -> TestRunner:
    return TestRunner()


def make_exercise(
    tests: list[TestDefinition],
    *,
    global_timeout: float = 5.0,
    exercise_timeout: float | None = None,
    language: str = "en",
) -> Exercise:
    cfg = ExerciseConfig(
        id="ex",
        statement="Test exercise",
        tests=tests,
        unit_test_timeout=exercise_timeout,
    )
    global_cfg = GlobalConfig(
        llm=LLMConfig(provider="ollama", model="llama3.2:3b", base_url="http://localhost:11434"),
        prompts=PromptConfig(
            on_success="s",
            on_failure="f",
            on_hints="h",
            on_no_llm="n",
        ),
        unit_test_timeout=global_timeout,
        language=language,
    )
    return Exercise(config=cfg, global_config=global_cfg)


INLINE_BOOL_CODE = """\
def test_add(add):
    return add(2, 3) == 5
"""

INLINE_TUPLE_CODE = """\
def test_add(add):
    result = add(2, 3)
    return result == 5, f"Expected 5, got {result}"
"""

INLINE_STDOUT_CODE = """\
def test_add(add):
    print("checking add")
    return add(2, 3) == 5
"""

INLINE_STUDENT_GLOBALS_CODE = """\
def test_via_globals(student_globals):
    add = student_globals.get("add")
    return callable(add) and add(1, 1) == 2
"""


# ---------------------------------------------------------------------------
# Basic pass/fail
# ---------------------------------------------------------------------------

class TestBasicPassFail:
    def test_passing_bool_return(self) -> None:
        td = TestDefinition(name="t1", code=INLINE_BOOL_CODE)
        ex = make_exercise([td])
        runner = make_runner()

        ns = {"add": lambda a, b: a + b}
        results = runner.run(ex, ns)

        assert len(results) == 1
        assert results[0].passed is True

    def test_failing_bool_return(self) -> None:
        td = TestDefinition(name="t1", code=INLINE_BOOL_CODE)
        ex = make_exercise([td])
        runner = make_runner()

        ns = {"add": lambda a, b: a - b}
        results = runner.run(ex, ns)

        assert results[0].passed is False

    def test_passing_tuple_return(self) -> None:
        td = TestDefinition(name="t1", code=INLINE_TUPLE_CODE)
        ex = make_exercise([td])
        results = make_runner().run(ex, {"add": lambda a, b: a + b})
        assert results[0].passed is True

    def test_failing_tuple_return_contains_message(self) -> None:
        td = TestDefinition(name="t1", code=INLINE_TUPLE_CODE)
        ex = make_exercise([td])
        results = make_runner().run(ex, {"add": lambda a, b: 0})
        assert results[0].passed is False
        assert "Expected 5, got 0" in (results[0].message or "")


# ---------------------------------------------------------------------------
# Stdout capture
# ---------------------------------------------------------------------------

class TestStdoutCapture:
    def test_stdout_captured_in_message(self) -> None:
        td = TestDefinition(name="t", code=INLINE_STDOUT_CODE)
        ex = make_exercise([td])
        results = make_runner().run(ex, {"add": lambda a, b: a + b})
        assert results[0].passed is True
        assert "checking add" in (results[0].message or "")


# ---------------------------------------------------------------------------
# Namespace injection
# ---------------------------------------------------------------------------

class TestNamespaceInjection:
    def test_parameter_by_name(self) -> None:
        td = TestDefinition(name="t", code=INLINE_BOOL_CODE)
        ex = make_exercise([td])
        # add is injected by parameter name
        results = make_runner().run(ex, {"add": lambda a, b: a + b})
        assert results[0].passed is True

    def test_missing_symbol_fails_gracefully(self) -> None:
        td = TestDefinition(name="t", code=INLINE_BOOL_CODE)
        ex = make_exercise([td])
        # "add" not in namespace
        results = make_runner().run(ex, {})
        assert results[0].passed is False
        assert "add" in (results[0].message or "")

    def test_missing_symbol_uses_configured_language(self) -> None:
        td = TestDefinition(name="t", code=INLINE_BOOL_CODE)
        ex = make_exercise([td], language="fr")

        results = make_runner().run(ex, {})

        assert results[0].passed is False
        assert (
            translate("runner_missing_student_name", {"name": "add"}, language="fr")
            == results[0].message
        )

    def test_student_globals_injection(self) -> None:
        td = TestDefinition(name="t", code=INLINE_STUDENT_GLOBALS_CODE)
        ex = make_exercise([td])
        ns = {"add": lambda a, b: a + b}
        results = make_runner().run(ex, ns)
        assert results[0].passed is True


# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------

class TestExceptionHandling:
    def test_exception_in_test_is_caught(self) -> None:
        code = """\
def test_crash(add):
    raise RuntimeError("boom")
"""
        td = TestDefinition(name="t", code=code)
        ex = make_exercise([td])
        results = make_runner().run(ex, {"add": lambda a, b: a + b})
        assert results[0].passed is False
        assert "boom" in (results[0].message or "")

    def test_exception_in_student_code_captured(self) -> None:
        code = """\
def test_raises(add):
    add(1)   # wrong arity → TypeError
    return True
"""
        td = TestDefinition(name="t", code=code)
        ex = make_exercise([td])
        results = make_runner().run(ex, {"add": lambda a, b: a + b})
        assert results[0].passed is False


# ---------------------------------------------------------------------------
# External module loading
# ---------------------------------------------------------------------------

class TestExternalModuleLoading:
    def test_module_import_failure_fails_gracefully(self) -> None:
        td = TestDefinition(name="t", module="nonexistent.module.xyz", function="fn")
        ex = make_exercise([td])
        results = make_runner().run(ex, {})
        assert results[0].passed is False

    def test_external_module_with_bool_return(self) -> None:
        td = TestDefinition(
            name="t",
            module="tests.test_external_helper",
            function="test_add_via_external_module",
        )
        ex = make_exercise([td])
        results = make_runner().run(ex, {"add": lambda a, b: a + b})
        assert results[0].passed is True

    def test_external_module_with_tuple_return(self) -> None:
        td = TestDefinition(
            name="t",
            module="tests.test_external_helper",
            function="test_with_message_via_external_module",
        )
        ex = make_exercise([td])
        results = make_runner().run(ex, {"add": lambda a, b: a + b})
        assert results[0].passed is True
        assert "Expected 30, got 30" in (results[0].message or "")

    def test_external_module_failure_shows_message(self) -> None:
        td = TestDefinition(
            name="t",
            module="tests.test_external_helper",
            function="test_with_message_via_external_module",
        )
        ex = make_exercise([td])
        results = make_runner().run(ex, {"add": lambda a, b: 0})
        assert results[0].passed is False
        assert "Expected 30, got 0" in (results[0].message or "")


# ---------------------------------------------------------------------------
# Multiple tests
# ---------------------------------------------------------------------------

class TestMultipleTests:
    def test_multiple_tests_all_run(self) -> None:
        code1 = "def test_a(add): return add(1,1) == 2"
        code2 = "def test_b(add): return add(2,2) == 4"
        tds = [
            TestDefinition(name="t1", code=code1),
            TestDefinition(name="t2", code=code2),
        ]
        ex = make_exercise(tds)
        results = make_runner().run(ex, {"add": lambda a, b: a + b})
        assert len(results) == 2
        assert all(r.passed for r in results)


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------

class TestTimeoutHandling:
    def test_timeout_fails_and_cancels_unit_test(self) -> None:
        code = """\
def test_slow(add):
    import time
    time.sleep(2)
    return True
"""
        td = TestDefinition(name="slow", code=code)
        ex = make_exercise([td], global_timeout=0.2)
        start = time.monotonic()

        results = make_runner().run(ex, {"add": lambda a, b: a + b})

        assert time.monotonic() - start < 1.5
        assert results[0].passed is False
        assert "timed out after 0.2 seconds" in (results[0].message or "")
        assert "cancelled" in (results[0].message or "")

    def test_exercise_timeout_overrides_global_timeout(self) -> None:
        code = """\
def test_slow(add):
    import time
    time.sleep(2)
    return True
"""
        td = TestDefinition(name="slow", code=code)
        ex = make_exercise([td], global_timeout=5.0, exercise_timeout=0.2)

        results = make_runner().run(ex, {"add": lambda a, b: a + b})

        assert results[0].passed is False
        assert "timed out after 0.2 seconds" in (results[0].message or "")
