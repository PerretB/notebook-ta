# notebook-ta

`notebook-ta` adds an LLM-powered teaching assistant to Jupyter notebooks for
Python programming courses. Students write answers in ordinary notebook cells
tagged with the `%%notebook_ta` magic; the package runs instructor-defined unit
tests, shows the results in the notebook, and streams tutor feedback or hints
from a configured LLM.

The import name is `notebook_ta`; the package/CLI name is `notebook-ta`.

## Project Overview

### End user features

- Work directly inside Jupyter notebooks with a single student-facing cell magic:
  `%%notebook_ta <exercise_id>`.
- Get immediate unit test feedback after running an answer cell.
- Receive streamed Markdown feedback from an LLM when tests pass.
- Ask for progressively more specific hints when tests fail.
- Keep working even if the LLM is unavailable: tests still run and a configured
  fallback message is shown.
- See clear notebook output for pass/fail status, test messages, and streamed model responses.

### Teacher features

- Author exercises declaratively in TOML: no Python setup code is required in the
  notebook for common exercises.
- Configure global prompts, per-exercise prompt overrides, LLM provider settings,
  test timeouts, and hint history length.
- Define tests inline in TOML or reference reusable external Python test modules.
- Use local Ollama models or OpenAI-compatible servers such as LM Studio, vLLM,
  and compatible Ollama endpoints.
- Let `model = "auto"` select from configured local models based on detected RAM
  and GPU VRAM.
- Use the benchmark GUI to compare prompts, models, student solutions, test
  outcomes, and generation metrics before publishing material to students.

## Quick Start

### Install

`notebook-ta` requires Python 3.11 or newer.

```bash
pip install notebook-ta
```

For local LLM use with Ollama, install Ollama separately [https://ollama.com/](https://ollama.com/).


### Create a Teacher Configuration

Create `global_config.toml` for provider settings and shared tutor prompts:

```toml
unit_test_timeout = 5.0

[llm]
provider = "ollama"
model = "llama3.2:3b"
base_url = "http://localhost:11434"
timeout = 120
temperature = 0.5
streaming = true

[prompts]
on_success = """
The student's code passed all tests. Give concise feedback on correctness,
clarity, style, and possible improvements.
"""

on_failure = """
The student's code failed one or more tests. Give targeted guidance without
revealing the full solution. Ask questions and suggest what to inspect next.
"""

on_no_llm = """
The LLM is not available right now, but your code was still checked against the
unit tests.
"""

hint_history_length = 3
```

Create `exercises.toml` with exercise definitions and tests:

```toml
[exercises.ex1]
name = "Addition"
statement = "Write a function `add(a, b)` that returns the sum of two numbers."

[[exercises.ex1.tests]]
name = "add(2, 3) == 5"
code = """
def test_add_basic(add):
    result = add(2, 3)
    return result == 5, f"Expected 5, got {result}"
"""

[[exercises.ex1.tests]]
name = "add(-1, 1) == 0"
code = """
def test_add_negative(add):
    result = add(-1, 1)
    return result == 0, f"Expected 0, got {result}"
"""
```

### Use It in a Notebook

In a setup cell:

```python
import notebook_ta

notebook_ta.load("global_config.toml", "exercises.toml")
```

In a student answer cell:

```python
%%notebook_ta ex1
def add(a, b):
    return a + b
```

When the cell runs, `notebook-ta` executes the student's code, runs the tests
for `ex1`, and displays either a success analysis or test failures with a hint
button.

See the complete example files in [docs/examples](docs/examples).

## Advanced Features

### Configuration and loading

- Load both configuration files from local paths or `https://` URLs.
- Override LLM settings at load time with `llm_overrides`.
- Enable prompt inspection and DEBUG logging with `debug=True`.
- Use `notebook_ta.get_registry()` to inspect registered exercises.

```python
notebook_ta.load(
    "global_config.toml",
    "exercises.toml",
    llm_overrides={"model": "llama3.2:1b"},
    debug=True,
)
```

### LLM providers

- `ollama`: uses Ollama's native generation API.
- `openai_compat`: uses the OpenAI-compatible chat completions API for local or
  hosted compatible servers.
- Streaming responses are supported and rendered progressively in the notebook.
- Availability checks fail closed: connection errors do not crash the notebook.

### Hardware-based model selection

Set `model = "auto"` and provide `[[llm.available_models]]` entries:

```toml
[llm]
provider = "ollama"
model = "auto"
base_url = "http://localhost:11434"

[[llm.available_models]]
name = "llama3.2:1b"
description = "Fast CPU-friendly model"
min_ram_gb = 4.0
min_vram_gb = 0.0

[[llm.available_models]]
name = "llama3.2:3b"
description = "Better quality when memory allows"
min_ram_gb = 8.0
min_vram_gb = 0.0
```

On `notebook_ta.load()`, the setup wizard detects available hardware and picks
the largest configured model that fits.

### Exercise authoring

- Add optional `additional_info` for constraints, examples, complexity notes, or
  grading context.
- Override prompts per exercise with `prompt_on_success` and
  `prompt_on_failure`.
- Set a global `unit_test_timeout`, then override it per exercise when needed.
- Use external tests with `module` and `function` for shared test libraries.
- Use `student_globals` when a test needs the full notebook namespace.

```toml
[exercises.ex2]
name = "Reverse List"
statement = "Write `reverse_list(lst)` without mutating the input."
additional_info = "Do not use `list.reverse()` or slice notation."
unit_test_timeout = 10.0
prompt_on_failure = "Give a conceptual hint about list construction."

[[exercises.ex2.tests]]
name = "Original list not modified"
code = """
def test_no_mutation(reverse_list):
    original = [1, 2, 3]
    copy = list(original)
    reverse_list(original)
    return original == copy, "The original list was modified."
"""
```

### Notebook-embedded statements

Teachers can keep exercise text in notebook Markdown instead of duplicating it
in `exercises.toml`:

````markdown
<div id="ex1">

## Exercise 1

Write a function `add(a, b)` that returns `a + b`.

</div>
````

Then load with an explicit notebook path if automatic detection is not reliable:

```python
notebook_ta.load(
    "global_config.toml",
    "exercises.toml",
    notebook_path="lesson.ipynb",
)
```

## The Bench CLI

`notebook-ta` includes a local NiceGUI benchmarking app for instructors who want
to compare prompts and models before using them in class.

Launch it with:

```bash
notebook-ta bench
notebook-ta bench my_project.json
```

The app opens in a browser and stores work in a JSON project file. It supports:

- creating or reopening benchmark projects;
- loading an exercise TOML catalog;
- adding, editing, tagging, and testing example student solutions;
- generating draft solutions with an internal model;
- configuring Python paths, autosave, and tag colors;
- editing `on_success` and `on_failure` prompts;
- running benchmark batches across one or more models;
- freezing prompt versions for reproducible historical results;
- comparing output in a matrix by exercise, solution, model, and prompt version;
- reviewing exact prompts, test results, timing metrics, throughput, errors, and
  stale-result warnings;
- deleting runs and re-running changed inputs.

See [docs/benchmarking.md](docs/benchmarking.md) for the full workflow.

## Documentation

- [Configuration reference](docs/configuration.md)
- [Authoring exercises](docs/authoring_exercises.md)
- [Benchmarking guide](docs/benchmarking.md)
- [Example configuration and notebook](docs/examples)

## Development

```bash
py -3.11 -m pip install -e ".[dev]"
py -3.11 -m pytest tests/
py -3.11 -m ruff check notebook_ta/ tests/
py -3.11 -m mypy notebook_ta/
```

## License

MIT License. See [LICENSE](LICENSE) for details.
