# notebook-ta Agent Guidelines

Full project description: [PROJECT.md](PROJECT.md)  
Detailed architecture: [Architecture.md](Architecture.md)


## Agent guidelines
- All changes must be tested with `pytest`
- Doc strings are required on all public functions and class methods
- Update Documentation in `docs/` for any public API changes
- Update dependencies in `pyproject.toml` if new packages are added to the project
- Update developer documentation for any architecture changes (see [Architecture.md](Architecture.md))

---

## Architecture

`notebook-ta` is a Python package that integrates an LLM-powered teaching assistant into Jupyter
notebooks. The package is structured around five decoupled layers: configuration, LLM connection,
exercise definition, unit test execution, and notebook integration.

Key structural facts:
- Import name: `notebook_ta` — PyPI name: `notebook-ta`
- Minimum Python version: **3.11** 
- Public API surface: `notebook_ta.load()` and `notebook_ta.get_registry()`
- Configuration is TOML-only (no programmatic config objects exposed to instructors)
- The `%%notebook_ta` IPython cell magic is the sole student-facing interface

See [Architecture.md](Architecture.md) for module layout, data models, component interaction
diagrams, and the full file tree.

---

## Build and Test

```bash
# Install in editable mode with all dev dependencies
py -3.11 -m pip install -e ".[dev]"

# Run the full test suite
py -3.11 -m pytest tests/

# Lint
py -3.11 -m ruff check notebook_ta/ tests/

# Type-check
py -3.11 -m mypy notebook_ta/
```

CI runs on Python 3.11 and 3.12 across Ubuntu, macOS, and Windows — see
[.github/workflows/ci.yml](.github/workflows/ci.yml).

---

## Conventions

### Code style
- Follow **PEP 8**; line length ≤ 100 characters (enforced by `ruff`).
- Use `from __future__ import annotations` in every module for deferred evaluation of type hints.
- Type hints are required on all public functions and class methods (`mypy --strict`).

### Pydantic models
- All configuration models live in `notebook_ta/config/models.py` and use **Pydantic v2**.
- Validation errors must be re-raised as `ConfigurationError` with a descriptive message.
- Never expose raw Pydantic validation errors to end users.

### LLM providers
- New providers must subclass `LLMProvider` (`llm/base.py`) and implement `query`, `stream`,
  `is_available`, and `from_config`.
- Register new providers in the `create_provider()` factory in `llm/base.py`.
- `is_available()` must never raise — return `False` on any connection error.

### Test runner
- Inline test code (`code` field) is `exec()`'d into an isolated namespace — never into the
  student's namespace.
- All test execution exceptions must be caught and returned as a failed `TestResult`, not re-raised.

### Notebook integration
- All display output must go through the helpers in `notebook/display.py` — do not call
  `IPython.display.display` directly from `magic.py`.
- `nest_asyncio.apply()` is called once in `notebook_ta.load()` — do not call it elsewhere.
- `SessionState` is owned by the `NotebookTAMagic` instance and lives for the kernel session lifetime.

### CLI
- CLI commands are defined with `click` in `cli/scaffold.py`.
- The entry point is `notebook-ta` (see `pyproject.toml`).

### Testing
- Mock `httpx` calls with `pytest-httpx`.
- Mock IPython shell with a minimal `MagicMock` stub; pass `shell=None` to `NotebookTAMagic`
  and set `.shell` after construction (traitlets validates the constructor argument).
- `nbformat` stores cell `source` as a list of strings — join before asserting substrings.
- Do not use `asyncio.coroutine` (removed in Python 3.11).

---

## Design Principles

- **Graceful degradation**: if the LLM is unreachable, show the `on_no_llm` message and unit test
  results — never raise an unhandled exception to the student.
- **Instructor simplicity**: no Python required from instructors; all configuration is declarative
  TOML.
- **Prompt injection safety**: `build_prompt()` includes a system preamble that instructs the LLM
  to ignore any directives embedded in student code.
- **Modularity**: LLM providers, test runners, and display components are independently replaceable.
  Add a new provider, test style, or display format without touching other layers.
