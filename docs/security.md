# Trust and Security Model

`notebook-ta` is a local teaching and authoring tool, not a sandbox for hostile Python. It assumes
that the operating environment and instructor-controlled inputs are trusted. Student answer code
runs as ordinary notebook code with the notebook kernel user's permissions.

This page describes the current security boundary so that instructors can choose an appropriate
deployment.

## Trusted and untrusted inputs

Treat these inputs as trusted:

- notebooks and every Python cell executed in them;
- exercise TOML files, inline test code, and external test modules;
- benchmark project JSON files, including saved solution and setup code;
- local Python modules made importable through benchmark Python-path settings;
- remote configuration URLs and the server that supplies their content.

Opening a file is not itself intended to execute its saved Python fields, but running a notebook
cell, previewing benchmark tests, or starting a benchmark run does. Do not run materials received
from an untrusted student or third party on an instructor workstation without separate OS-level
isolation.

Configuration files loaded over HTTPS receive transport protection, but notebook-ta does not sign,
pin, or independently authenticate their content.

## Execution boundaries

| Mechanism | What it provides | What it does not provide |
|---|---|---|
| Separate namespace/dictionary | Reduces accidental name collisions between setup, solution, and test code | No restriction on imports, files, environment variables, subprocesses, or network access |
| Wall-clock timeout | Lets notebook tests and benchmark workers cancel a direct process that exceeds the configured duration | No CPU/memory limit and no guarantee that descendant processes are terminated |
| Child process | Keeps most test-callable failures and benchmark preview/run failures out of the notebook kernel or GUI server process | No privilege boundary: the child inherits the same user identity and generally the same filesystem, environment, and network access |
| Loopback benchmark binding | Limits the GUI listener to the local machine (`127.0.0.1`) | No authentication or authorization; other processes/users able to reach that local listener are not distinguished |
| OS sandbox/container/VM | Can provide a restricted identity, filesystem, network, resources, and process tree | Not created or managed by notebook-ta |

An “isolated namespace” is therefore only Python name separation. A timeout-bounded worker is an
availability and fault-containment mechanism, not a security sandbox.

### Notebook path

The body of a `%%notebook_ta` cell runs first in the persistent IPython kernel namespace. It has
the same capabilities as any other notebook cell. If compilation or execution fails, notebook-ta
now stops before tests and LLM analysis, but this does not undo side effects that occurred before a
runtime error.

Inline test source is resolved in the notebook process before its callable is sent to a
timeout-bounded child. Consequently, top-level statements in inline tests can execute in the
kernel. Importing an external test module can likewise execute that module's top-level code in the
kernel. The test callable itself runs in a child process with the kernel user's OS permissions.

### Benchmark path

The benchmark server binds explicitly to loopback and is intended for one trusted local operator.
It has no authentication and must not be exposed through a non-loopback bind, reverse proxy, port
forward, shared notebook service, or tunnel.

Editable solution, setup, and test execution for previews and benchmark jobs is routed through a
timeout-bounded worker rather than executed directly in the NiceGUI server process. The worker can
still read and write files, inspect its environment, use the network, and create subprocesses as
the host user. Termination currently targets the direct worker, not an entire descendant process
tree.

Benchmark project files store source code, prompts, test results, model output, metrics, and
history. They do not store resolved API-key values; only environment-variable names are persisted.
Protect project files according to the sensitivity of student code and model output.

## LLM data boundary

Prompts can contain exercise statements, student source code, test results, diagnostics, and hint
history. Configuring a remote LLM sends that material to the configured endpoint. Instructors are
responsible for ensuring that the provider, retention policy, and student-data handling meet their
institutional and legal requirements.

API-key values are resolved from environment variables at runtime. Keep secrets out of notebooks,
TOML files, benchmark projects, source code, and debug output. Do not make unrelated credentials
available to a process that handles untrusted code.

## Running untrusted material

For arbitrary or student-supplied submissions, run the notebook kernel and benchmarking tool
inside a disposable OS-level boundary. At minimum:

1. Use a dedicated low-privilege identity or disposable container/virtual machine.
2. Mount only required course files, read-only where possible; do not mount home directories,
   SSH keys, cloud credentials, or host control sockets.
3. Disable network access unless a specific endpoint is required.
4. Apply CPU, memory, process-count, file-size, and wall-clock limits.
5. Terminate the whole process tree on timeout and discard the environment after use.
6. Provide only short-lived, narrowly scoped credentials when an external service is required.

Process workers supplied by notebook-ta are still useful inside that boundary, but they are not a
substitute for it.
