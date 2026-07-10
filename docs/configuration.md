# Configuration Reference

This document describes all configuration options for `notebook-ta`.

---

## File Overview

`notebook-ta` uses two TOML configuration files:

| File | Purpose |
|------|---------|
| `global_config.toml` | LLM provider settings, default prompts |
| `exercises.toml` | Exercise definitions and unit tests |

Both files can be loaded from a **local path** or an **`https://` URL**.

---

## `global_config.toml`

### `[llm]` — LLM Provider Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `provider` | string | `"ollama"` | LLM backend: `"ollama"` or `"openai_compat"` |
| `model` | string | — | Model name, or `"auto"` to trigger hardware-based auto-selection |
| `base_url` | string | — | API endpoint URL |
| `api_key` | string | `null` | API key (optional for local providers) |
| `timeout` | integer | `120` | Request timeout in seconds |
| `temperature` | float | `0.7` | Sampling temperature (0.0 = deterministic, higher = more creative) |
| `streaming` | boolean | `true` | Enable streaming responses |

#### `[[llm.available_models]]` — Auto-selection Candidates

Used only when `model = "auto"`. The system selects the model with the highest `min_ram_gb` whose
requirements are met by the detected hardware.

| Key | Type | Description |
|-----|------|-------------|
| `name` | string | Model identifier (e.g. `"llama3.2:3b"`) |
| `description` | string | Human-readable label shown during auto-selection |
| `min_ram_gb` | float | Minimum system RAM in GB |
| `min_vram_gb` | float | Minimum GPU VRAM in GB (`0` means CPU-only is fine) |

### `[prompts]` — Default Prompt Templates

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `on_success` | string | — | Prompt when all tests pass |
| `on_failure` | string | — | Prompt when tests fail, and for all subsequent hint requests |
| `on_no_llm` | string | — | Message shown when LLM is unreachable |
| `hint_history_length` | integer | `3` | Max previous hint exchanges included in context |

### Global Unit Test Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `unit_test_timeout` | number | `5.0` | Maximum wall-clock seconds allowed for each configured unit test. Timed-out tests are cancelled and reported as failures. |

### Internationalization

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `language` | string | `"en"` | Language code for notebook-facing messages and labels. Built-in languages are `"en"` and `"fr"`. Unsupported values emit a log warning and fall back to English. |

---

## `exercises.toml`

Each exercise is declared under `[exercises.<id>]`.

### Exercise Fields

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `statement` | string | ❌ | Exercise description passed to the LLM. May be omitted if the statement is embedded in the notebook (see [Embedding statements in the notebook](authoring_exercises.md#embedding-statements-in-the-notebook)) |
| `additional_info` | string | ❌ | Any other context for the LLM |
| `prompt_on_success` | string | ❌ | Overrides global `on_success` |
| `unit_test_timeout` | number | optional | Overrides the global unit test timeout for this exercise |
| `prompt_on_failure` | string | ❌ | Overrides global `on_failure` |

> **Note** — either `statement` in the TOML *or* a `<div id="<id>">` block in the notebook markdown must be provided for every exercise.  If neither is present, `notebook_ta.load()` raises a `ConfigurationError`.

### `[[exercises.<id>.tests]]` — Unit Tests

| Key | Type | Description |
|-----|------|-------------|
| `name` | string | Human-readable test name |
| `code` | string | Inline Python function source |
| `module` | string | Dotted module path for external test |
| `function` | string | Function name within the external module |

Exactly one of `code` or (`module` + `function`) must be specified.

---

## Example

```toml
unit_test_timeout = 5.0
language = "en"

[llm]
provider = "ollama"
model = "auto"
base_url = "http://localhost:11434"

[[llm.available_models]]
name = "llama3.2:3b"
description = "3B model — recommended"
min_ram_gb = 8.0
min_vram_gb = 0.0

[prompts]
on_success = "The student passed all tests. Analyse the solution..."
on_failure = "The student failed tests. Provide targeted hints..."
on_no_llm = "LLM unavailable. Check your Ollama installation."
hint_history_length = 3
```
