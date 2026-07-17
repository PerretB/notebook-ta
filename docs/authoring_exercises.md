# Authoring Exercises

This guide explains how to write exercises and unit tests for `notebook-ta`.

---

## Exercise Structure

Each exercise is defined in `exercises.toml` under `[exercises.<id>]`:

```toml
[exercises.ex1]
name = "Add two numbers"
statement = "Write a function `add(a, b)` that returns the sum of two numbers."
additional_info = "No imports are needed."
```

The `id` (here `ex1`) is the stable identifier used in the `%%notebook_ta` cell magic line.
The optional `name` is an editable display name used by the benchmarking interface; changing it
does not break saved solutions or historical benchmark records.

`statement` is optional — see [Embedding statements in the notebook](#embedding-statements-in-the-notebook) for an alternative that avoids duplicating the exercise description.

---

## Writing Unit Tests

Tests are declared as TOML array tables: `[[exercises.<id>.tests]]`.

Exercise tests are trusted Python. Namespace separation and test timeouts are not a security
sandbox; see the [trust and security model](security.md) before running third-party material.

### Inline Tests

Use the `code` field to write a Python function directly in the TOML file:

```toml
[[exercises.ex1.tests]]
name = "add(2, 3) == 5"
code = """
def test_add(add):
    result = add(2, 3)
    return result == 5, f"Expected 5, got {result}"
"""
```

The runner inspects the test function's signature and resolves every parameter name in the
student's IPython namespace. In this example, the `add` parameter receives the object stored under
the name `add`. Multiple parameters are resolved independently in the same way.

Resolution happens before the test is called. If any parameter name is absent from the student's
namespace, the test is not executed and is reported as failed with a message identifying the
missing name. The reserved `student_globals` parameter follows the explicit export rules in
[Passing student symbols to tests](#passing-student-symbols-to-tests) instead.

It must return either:

- A `bool` (`True` = pass, `False` = fail)
- A `tuple[bool, str]` where the string is a human-readable message

Any text printed to stdout is also captured and included in the message. Common ANSI SGR color and
text-style sequences (including standard and bright colors, bold, and underline) are rendered in
the notebook output, so existing terminal-style custom test reports remain readable.

### External Tests

For complex tests, reference a function in an importable Python module:

```toml
[[exercises.ex3.tests]]
name = "Performance test"
module = "course_tests.ex3"
function = "test_performance"
```

For example, `course_tests/ex3.py` could contain:

```python
def test_performance(build_index):
    index = build_index(["alpha", "beta"])
    return len(index) == 2, "Expected an index containing both values."
```

The module must be importable from the notebook's working directory or `PYTHONPATH`. After loading
the configured function, the runner resolves its parameters exactly as it does for an inline test:
each parameter name is looked up in the student's IPython namespace. If any name is missing, the
function is not called and the test is reported as failed with the missing name. The reserved
`student_globals` parameter uses the shared rules below.

### Passing student symbols to tests

The following rules apply to both inline and external tests. Put `student_symbols` or
`export_student_globals` in the test's TOML table alongside either `code` or `module`/`function`.

#### Named parameters

Named parameters are the preferred way to pass student definitions to a test. Only the requested
objects are serialized for the isolated test process. For example, a function declared as
`def test_result(parse, render): ...` receives the student's `parse` and `render` objects. The test
fails before invocation if either name is not defined.

#### Exporting multiple symbols as a dictionary

When a test needs a dictionary of several student definitions, declare `student_symbols`. The
runner exports only those names and passes the resulting dictionary as `student_globals`:

```toml
[[exercises.ex2.tests]]
name = "Both functions are defined"
student_symbols = ["add", "mul"]
code = """
def test_both_defined(student_globals):
    has_add = "add" in student_globals and callable(student_globals["add"])
    has_mul = "mul" in student_globals and callable(student_globals["mul"])
    return has_add and has_mul, "Expected both add() and mul() to be defined."
"""
```

A missing selected symbol is reported as a failed test. A test that declares a
`student_globals` parameter without either export option also fails with a configuration message.

The full IPython namespace can be exported explicitly with
`export_student_globals = true`, but this is strongly discouraged. Notebook namespaces commonly
contain large objects, open resources, module state, or objects that `cloudpickle` cannot serialize.
Exporting all of them can therefore make tests slow or cause process preparation to fail even when
the objects relevant to the test are valid. Use named parameters or `student_symbols` whenever
possible.

### Unit Test Timeouts

Each unit test is cancelled if it runs longer than the global `unit_test_timeout` from
`global_config.toml`. The default is 5 seconds. A timeout is reported as a failed test in the
notebook and in benchmark runs, and the timeout message is included in the LLM prompt.

Override the timeout for one exercise with `unit_test_timeout`:

```toml
[exercises.ex_slow]
statement = "Implement a function that handles a large input."
unit_test_timeout = 15.0
```

---

## Exercise-Level Prompt Overrides

You can override the global prompts for a specific exercise:

```toml
[exercises.ex_hard]
statement = "Implement Dijkstra's algorithm."
prompt_on_success = "Excellent! Analyse the time and space complexity of this graph algorithm."
prompt_on_failure = "Graph algorithms can be tricky. Think about the data structures you need. When the student asks for hints, escalate guidance gradually."
```

---

## Embedding Statements in the Notebook

To avoid duplicating the exercise description in both the notebook and `exercises.toml`, you can
omit `statement` from the TOML and embed it directly in a notebook markdown cell using a
`<div id="<exercise-id>">` block:

````markdown
<div id="ex1">

## Exercise 1 — Add two numbers

Write a function `add(a, b)` that returns the sum of `a` and `b`.

Example:
```python
add(2, 3)  # → 5
```

</div>
````

The div renders normally in Jupyter and its inner content is used as the statement sent to the LLM.
Multiple markdown cells with the same `id` are concatenated in document order.

To use this feature, pass `notebook_path=` to `notebook_ta.load()`:

```python
import notebook_ta
notebook_ta.load(
    "global_config.toml",
    "exercises.toml",
    notebook_path="my_notebook.ipynb",  # path to the current notebook
)
```

If `notebook_path` is not provided, `notebook-ta` will try to detect the notebook path
automatically.  Pass it explicitly when auto-detection
fails or for reproducibility.

> **Error handling** — if `statement` is absent from both the TOML and the notebook, `load()`
> raises a `ConfigurationError` identifying the affected exercise.

---

## Complete Example

```toml
[exercises.reverse]
statement = """
Write a function `reverse_list(lst)` that returns a new list
with the elements in reverse order.
"""
additional_info = "Do not use lst[::-1] or lst.reverse()."

[[exercises.reverse.tests]]
name = "reverse_list([1,2,3]) == [3,2,1]"
code = """
def test_basic(reverse_list):
    return reverse_list([1,2,3]) == [3,2,1], "Basic reversal failed"
"""

[[exercises.reverse.tests]]
name = "Empty list returns empty list"
code = """
def test_empty(reverse_list):
    return reverse_list([]) == [], "Empty list should return []"
"""

[[exercises.reverse.tests]]
name = "Original list not modified"
code = """
def test_no_mutation(reverse_list):
    lst = [1, 2, 3]
    copy = list(lst)
    reverse_list(lst)
    return lst == copy, "The original list was mutated!"
"""
```

---

## Tips

- Keep test names short and descriptive — they appear in the notebook output.
- Return a meaningful message from your tests to help students understand failures.
- Use `print()` inside test functions to emit additional diagnostic information.
- Prefer named test parameters; use `student_symbols` only when the test needs a dictionary.
- External module tests are useful for complex or reusable test logic shared across exercises.
