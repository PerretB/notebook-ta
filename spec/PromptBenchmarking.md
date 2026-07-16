Functional Specification: "Notebook TA" Benchmarking Tool

1. Project Overview & Objective
The purpose of this tool is to provide a graphical interface to evaluate, optimize, and compare the performance of various LLMs and system prompts. This tool serves the Notebook-ta pedagogical project, helping educators find the optimal combination of model and prompt to deliver immediate, high-quality, and pedagogically sound feedback to students.

The application is distributed wihtin the notebook-ta project. Running a simple command-line interface (CLI) command automatically launches the user interface in a browser (Python with NiceGUI).

2. User Interface Layout
The interface is composed of a Main Panel featuring several functional tabs.

+-----------------------------------------------------------------------+
|  [Main Panel]                                                         |
|  Tabs: [1. Settings] [2. Exercises] [3. Runner] [4. Compare]          |
|  -------------------------------------------                          |
|                                                                       |
|  (Content of the actively selected tab)                               |
|                                                                       |
+-----------------------------------------------------------------------+

The main roles of the functional tabs are:

- Settings: General project settings, load/save project file
- Exercises: Definition of the exercises used in the benchmarks : statements, additional information, student solutions, unit tests...
- Runner: Definition of the general prompts to be tested, choice of the models to be tested, button to start running tests.
- Compare: Comparison matrix between different test run.


3. Main use-case 

The user starts the application as a command line CLI, e.g. `$ notebook-ta bench`. A welcome
modal offers the most recent project, an existing-project file picker, and new-project creation.
Creating a project requires a project name and an exercises TOML file. The project name supplies
the default JSON filename and the tag vocabulary starts with common solution-quality tags.

Starting from a new project, the user will start defining exercises. For each exercise we have at least the exercise statement and one or more student solutions.

When all the exercises are prepared the user can define the general prompts and select the models he wants to test in the Runner tab. Clicking on "Run Benchmark" will start testing the different prompts and models on the all the (exercise, student solution) pairs. The application collects the LLM answers and classical metrics such as the time-to-first-token, the total token used, the generation time...

When tests have finished running the user can explore the LLMs answers and compare the different prompts/models in the compare tab in the form of comparison matrix.

4. Lifecycle Management

Full-State Serialization: Saving the project exports a single JSON file containing the file path of the source TOML catalog, all user-added student responses, the chronological library of system prompts, and the complete execution history (including outputs, metrics, and input-snapshots).


To ensure reliable benchmarking over time, the application strictly separates the current configuration from past results using two core mechanisms:

A. Prompt Versioning (Snapshots)
Active Workspace: The user adjusts the system prompt and selects target models in real-time.

Execution Freeze: The moment the user clicks "Run Benchmark," the active prompt is frozen, timestamped, and assigned a version ID (e.g., Prompt V1, Prompt V2).

Prompt Recall: Changing the prompt in the active workspace does not alter past results. Users can browse the history of prompts and reload any previous version back into the active editor.

B. Input Data Mutations (Stale Flag Strategy)
To handle cases where an instructor modifies an exercise prompt or updates a student's sample code after a benchmark has already run, the tool implements a Stale Flag Strategy:

Data Snapshots: Every execution record stores not just the LLM's output, but a complete snapshot of the exact inputs used at that moment (possibly a hash of the inputs).

Drift Detection: In the comparison view, the tool compares the live inputs with the snapshot inputs tied to the saved LLM response.

Visual Warning: If the live exercise text or student code has changed, the old LLM response remains visible but is visually grayed out and flagged as "⚠️ Stale (Inputs Modified)". A localized "Re-run" button appears next to it to allow the user to refresh that specific test case.


5. Settings tab

The settings tab enable to define global project settings. 

It contains:
- actions to save the project under a new name and to close it, returning to the welcome modal.
- a confirmation before closing a project with unsaved changes.
- an LLM model selection (dropdown list), called internal model, used for internal purpose like automatically generating fake user answers or evaluating tested LLM answers.
- directories that should be added to the Python path for external code loading such as unit tests.
- an option to activate or deactivate auto-save.
- an editable color for each tag, used consistently for tag badges throughout the application.

6. Exercise tab

The exercise tab enables editing exercises imported from the TOML catalog selected during project
creation. It is possible to indicate a related notebook file where exercise statements should be
read if needed.

For each exercise, the user can add one or several student solutions. Each solution can be annotated with user defined tags (like tags in Github issues), for example "correct", "wrong complexity", "logic flow", "missing edge-case"... The user can ask the internal model to generate a student solution based on the exercise statement and a selection of tags. The user should be able to define, run and see the results of the unit-tests on the sudent solution.


7. Runner Tab
This tab handles:
 - the definition of the general prompts to be tested (on_success prompt and on_failure prompt)
 - the selection of the models to be tested
 - the execution of the tests. 

Trigger: A prominent "Run Benchmark" button starts the execution queue. The application generates a matrix of all combinations:  [All Created Exercises] × [All Associated Student Submissions] for the given prompts.

Real-time Monitoring: A global progress bar and a live data table display the status of each job (Pending, Generating, Completed).

Non-blocking UI: The generation process runs entirely asynchronously. The user can navigate to other tabs, modify code, or edit text without freezing the application.

Service Disconnection Resilience: If the local LLM server (Ollama) is stopped or unreachable, the application must remain interactive. It should display a clear error notification to the user, pause the execution queue gracefully, and offer a retry option without crashing the UI.

Notifications: The application should provide real-time notifications for key events such as job completion, errors, and warnings.

8. Compare tab

The analytical core of the tool, used to evaluate variations over time.

A matrix view allows the user to compare the LLM outputs for a specific exercise and a specific student solution across different prompt versions and models.


- The last test runs are displayed by default, but the user can select any previous test run. A multi-select list displays all historical combinations of [Model Name + Prompt Version] that have run for this specific context. The user checks the ones they want to compare side-by-side.
- Comparison Columns: The selected configurations are rendered as adjacent vertical columns. Each column displays:
  - Header Information: Model name and the prompt version ID/timestamp.
  - Performance Badges: Visual cards tracking latency and generation speed.
  - Feedback Output: The full text response from the LLM, rendered natively in Markdown with appropriate code syntax highlighting.
- Each line of the matrix corresponds to a specific exercise and a specific student solution. When an exercise has multiple student solutions, each solution is displayed in a separate line. The lines are grouped by exercise and can be collapsed or expanded for easier navigation.
- Exercises and solutions can be filtered by user-defined tags.
- If the output of a previous test run is stale (i.e., the exercise statement or student solution has changed since the last execution), the corresponding cell is visually grayed out and flagged with a "⚠️ Stale (Inputs Modified)" warning. A "Re-run" button is provided to allow the user to refresh that specific test case and obtain updated results.
- The cells in the comparison matrix are interactive. Clicking on a cell opens a detailed view that includes:
  - The exact full prompt sent to the LLM for that run.
  - The unit test results for the student solution.
  - Performance metrics such as time-to-first-token, total generation time, and throughput.
  - Any associated error messages or warnings.


9. Performance Metrics to Capture
For every individual generation, the backend must capture and save the following non-functional metrics:

Time to First Token (TTFT): The duration (in seconds) between sending the payload and receiving the very first chunk of text from the local LLM stream.

Total Generation Time: The overall time taken to complete the response text.

Throughput (Generation Speed): Measured in tokens per second (or words per second) to evaluate if the model runs efficiently on the user's local hardware.

10. Project Persistence
Full-State Serialization: Saving the project exports a single file containing the file path of the source TOML catalog, all user-added student responses, the chronological library of system prompts, and the complete execution history (including outputs, metrics, and input-snapshots).

Credentials are never stored in the project file. Model settings persist only the name of an
environment variable containing an API key; its value is resolved in memory when the provider is
created.

A save button should be always available in the UI, and an auto-save option should be provided to automatically save the project at regular intervals or after significant changes. A warning should be displayed if the user attempts to close the application with unsaved changes.

