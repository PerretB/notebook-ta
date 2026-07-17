# Prompt/Model Benchmarking Tool

`notebook-ta` ships a local GUI tool that helps instructors iterate on system prompts and compare
LLM/model combinations before rolling them out to students. It is documented in detail in
[the functional spec](https://github.com/PerretB/notebook-ta/blob/main/spec/PromptBenchmarking.md) and
[the architecture spec](https://github.com/PerretB/notebook-ta/blob/main/spec/PromptBenchmarkingArchitecture.md)
(architecture).

## Launching

```bash
notebook-ta bench                    # show the project welcome screen
notebook-ta bench my_project.json    # offer this project on the welcome screen
```

This opens the benchmarking UI in your default browser. The welcome dialog lets you reopen the
most recent project, browse for another project, or create a new one. New projects require a name
and an exercises TOML file; the name becomes the suggested JSON filename on first save. Their tag
list starts with `correct`, `wrong complexity`, `logic flow`, and `missing edge-case`.

The server listens on `127.0.0.1` and has no authentication. It is intended for one trusted local
operator and must not be exposed through a proxy, tunnel, shared host, or non-loopback bind.
Editable Python runs in timeout-bounded workers with the host user's permissions; these workers
are not security sandboxes. Read the [trust and security model](security.md) before using
third-party projects or student submissions.

## Workflow

1. **Settings** — configure the *internal model* (used only to help draft example student
   solutions—never to score benchmark output), Python paths, tags, and autosave. Every tag has an
   editable color which is used for its badges throughout the app. **Save As** opens a native file
   picker. **Close project** returns to the welcome dialog; unsaved changes require explicit
   confirmation before they are discarded.
2. **Exercises** — exercises are expanded by default and their solution cards are arranged side by
   side with horizontal scrolling. Edit exercise and solution display names inline, append new
   exercises to a local TOML catalog, add solutions manually or with the internal model, tag them
   (e.g. `correct`, `wrong complexity`), and run their unit tests. For each exercise,
   benchmark-only setup code can define helper variables or functions before unit tests run; this
   setup is saved in the benchmark project JSON file, not in `exercises.toml`. Exercise edits
   preserve the catalog's comments and formatting; remote TOML catalogs are read-only.
3. **Runner** — write the `on_success` / `on_failure` prompts to test, select one or more models,
   and click **Run Benchmark**. Prompts are frozen into a versioned snapshot (`V1`, `V2`, ...) the
   moment you click Run, so past results always remain reproducible even if you keep editing the
   prompt afterward.
4. **Compare** — review results in a matrix whose rows are exercise/student-solution pairs and
   whose columns are historical model + prompt-version combinations. The latest run is selected by
   default; use the shared multi-select to compare other combinations and the tag filter to narrow
   the solution rows. Column headers show average TTFT, total generation time, and throughput for
   the visible results. The left column shows each solution's code and opens the full exercise
   statement. Click any result cell to inspect its exact prompt, unit tests, metrics, and errors.
   Runs can be permanently deleted from this tab after acknowledging that deletion cannot be
   undone; all results produced by that run are deleted with it. If the exercise or solution
   changed after generation, the cell is flagged **⚠️ Stale (Inputs Modified)** with a one-click
   **Re-run**.

## API credentials

The benchmark UI never accepts or stores an API key value. For the internal model and each model
under test, enter the **name of an environment variable** in the **API key environment variable**
field. Set that variable before launching the benchmark application. For example:

```powershell
$env:NOTEBOOK_TA_OPENAI_KEY = "your-api-key"
notebook-ta bench
```

```bash
export NOTEBOOK_TA_OPENAI_KEY="your-api-key"
notebook-ta bench
```

Enter `NOTEBOOK_TA_OPENAI_KEY`—not the key value itself—in the UI. The application resolves the
variable only when it creates the LLM provider. Local providers such as Ollama normally leave this
field empty.

Only the environment-variable name is saved in the benchmark project. The resolved secret is
kept in memory and is never written to project JSON. Ensure the variable is available in the
environment whenever you reopen the project and run that model.

## Project files

Everything (settings, per-exercise setup code, student solutions, prompt version history, and the
full execution history with metrics) is saved to a single JSON project file via the **Save** button
or autosave. API key values are excluded; project files contain only their environment-variable
references. The autosave interval must be a positive number of seconds.
