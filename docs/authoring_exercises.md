# Authoring Exercises

This guide explains how to write exercises and unit tests for `notebook-ta`.

---

## Exercise Structure

Each exercise is defined in `exercises.toml` under `[exercises.<id>]`:

```toml
[exercises.ex1]
name = "Add two numbers"
statement = "Write a function `add(a, b)` that returns the sum of two numbers."
expected_output = "5"
additional_info = "No imports are needed."
```

The `id` (here `ex1`) is the stable identifier used in the `%%notebook_ta` cell magic line.
The optional `name` is an editable display name used by the benchmarking interface; changing it
does not break saved solutions or historical benchmark records.

`statement` is optional — see [Embedding statements in the notebook](#embedding-statements-in-the-notebook) for an alternative that avoids duplicating the exercise description.

---

## Writing Unit Tests

Tests are declared as TOML array tables: `[[exercises.<id>.tests]]`.

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

The test function receives the student's symbol by parameter name.  
It must return either:
- A `bool` (`True` = pass, `False` = fail)
- A `tuple[bool, str]` where the string is a human-readable message

Any text printed to stdout is also captured and included in the message.

### Using `student_globals`

If your parameter is named `student_globals`, the entire student namespace (IPython `user_ns`) is
passed as that argument — useful when the student's code defines multiple names:

```toml
[[exercises.ex2.tests]]
name = "Both functions are defined"
code = """
def test_both_defined(student_globals):
    has_add = "add" in student_globals and callable(student_globals["add"])
    has_mul = "mul" in student_globals and callable(student_globals["mul"])
    return has_add and has_mul, "Expected both add() and mul() to be defined."
"""
```

### External Tests

For complex tests, reference a function in an importable Python module:

```toml
[[exercises.ex3.tests]]
name = "Performance test"
module = "course_tests.ex3"
function = "test_performance"
```

The module must be importable from the notebook's working directory or `PYTHONPATH`.

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
expected_output = "[3, 2, 1]"
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
- Use `student_globals` when you need to check that multiple names are defined.
- External module tests are useful for complex or reusable test logic shared across exercises.
