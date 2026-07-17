# notebook-ta

`notebook-ta` adds an LLM-powered teaching assistant to Jupyter notebooks for Python programming
courses. Students work with the `%%notebook_ta` cell magic, while instructors define exercises,
tests, and tutor prompts in TOML files.

```{toctree}
:maxdepth: 2
:caption: User Guide

configuration
authoring_exercises
benchmarking
security
release
```

```{toctree}
:maxdepth: 2
:caption: Reference

api
```

## Quick Start

Install the package:

```bash
pip install notebook-ta
```

Load the teaching assistant from a notebook setup cell:

```python
import notebook_ta

notebook_ta.load("global_config.toml", "exercises.toml")
```

Use the magic in a student answer cell:

```python
%%notebook_ta ex1
def add(a, b):
    return a + b
```

See the example configuration and notebook files in
[`docs/examples`](https://github.com/PerretB/notebook-ta/tree/main/docs/examples).
