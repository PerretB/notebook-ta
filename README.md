# notebook-ta

`notebook-ta` is a Python package that integrates an LLM-powered teaching assistant into Jupyter
notebooks for programming courses. Students write code in designated cells; on execution the
assistant automatically runs unit tests, triggers the LLM for analysis, and displays streaming
feedback directly in the notebook output.

## Installation

```bash
pip install notebook-ta
```

For local LLM setup support (hardware detection and rich CLI output):

```bash
pip install "notebook-ta[wizard]"
```

For the prompt/model benchmarking GUI (instructor-facing, see below):

```bash
pip install "notebook-ta[bench]"
```

## Quick Start

### 1. Create configuration files

**`global_config.toml`**

```toml
[llm]
provider = "ollama"
model = "llama3.2:3b"
base_url = "http://localhost:11434"
timeout = 120
streaming = true

[prompts]
on_success = "The student's code passed all tests. Provide a high-level analysis of the solution..."
on_failure = "The student's code failed some tests. Provide targeted feedback..."
on_hints = "The student is asking for hints. Use the hint history to escalate guidance..."
on_no_llm = "The LLM is not available. Please check your connection and try again."
hint_history_length = 3
```

**`exercises.toml`**

```toml
[exercises.ex1]
statement = "Write a function `add(a, b)` that returns the sum of two numbers."

[[exercises.ex1.tests]]
name = "Test add(2, 3) == 5"
code = """
def test_add(add):
    return add(2, 3) == 5, "Expected 5"
"""
```

### 2. Use in a Jupyter notebook

```python
# Setup cell
import notebook_ta
notebook_ta.load("global_config.toml", "exercises.toml")
```

```python
%%notebook_ta ex1
# Write your solution here
def add(a, b):
    return a + b
```

### 3. Scaffold a notebook from exercises

```bash
notebook-ta create-notebook exercises.toml --global-config global_config.toml --output notebook.ipynb
```

### 4. Check hardware for local LLM

```bash
notebook-ta setup
```

### 5. Benchmark prompts and models

```bash
notebook-ta bench
```

Launches a local GUI for iterating on system prompts and comparing LLM/model combinations. See
[docs/benchmarking.md](docs/benchmarking.md) for details.

## Configuration

See [docs/configuration.md](docs/configuration.md) for full configuration reference.

## Authoring Exercises

See [docs/authoring_exercises.md](docs/authoring_exercises.md) for the exercise authoring guide.

## Development

```bash
git clone https://github.com/your-org/notebook-ta
cd notebook-ta
pip install -e ".[dev]"
pytest
```

## License

MIT License. See [LICENSE](LICENSE) for details.
