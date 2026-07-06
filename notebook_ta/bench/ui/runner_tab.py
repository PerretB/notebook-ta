"""Runner tab: prompt drafting, model selection, and benchmark execution."""

from __future__ import annotations

from nicegui import ui

from notebook_ta.bench.executor import BenchJob
from notebook_ta.bench.models import ModelUnderTest
from notebook_ta.bench.state import BenchAppState
from notebook_ta.bench.ui._helpers import tracked_on_change
from notebook_ta.config.models import LLMConfig


def build(state: BenchAppState) -> None:
    """Render the Runner tab."""
    project = state.project

    with ui.card().classes("w-full"):
        ui.label("Prompts").classes("text-md font-bold")
        ui.textarea(
            "On success prompt",
            value=project.draft_prompt_on_success,
            on_change=tracked_on_change(state, project, "draft_prompt_on_success"),
        ).classes("w-full").props("rows=4")
        ui.textarea(
            "On failure prompt",
            value=project.draft_prompt_on_failure,
            on_change=tracked_on_change(state, project, "draft_prompt_on_failure"),
        ).classes("w-full").props("rows=4")

        with ui.row().classes("items-center gap-2"):
            ui.label("Prompt history:")
            version_select = ui.select(
                {pv.id: pv.id for pv in project.prompt_versions}, label="Load version"
            )

            def _recall() -> None:
                if not version_select.value:
                    return
                prompt_version = next(
                    p for p in project.prompt_versions if p.id == version_select.value
                )
                project.draft_prompt_on_success = prompt_version.on_success
                project.draft_prompt_on_failure = prompt_version.on_failure
                state.mark_dirty()
                ui.navigate.reload()

            ui.button("Recall", on_click=_recall)

    with ui.card().classes("w-full"):
        ui.label("Models Under Test").classes("text-md font-bold")

        models_container = ui.column()

        def _toggle_model(label: str, selected: bool) -> None:
            selected_set = set(project.draft_selected_model_labels)
            if selected:
                selected_set.add(label)
            else:
                selected_set.discard(label)
            project.draft_selected_model_labels = sorted(selected_set)
            state.mark_dirty()

        def _refresh_models() -> None:
            models_container.clear()
            with models_container:
                for model in project.models_under_test:

                    def _on_toggle(event, lbl=model.label) -> None:
                        _toggle_model(lbl, event.value)

                    with ui.row().classes("items-center gap-2"):
                        ui.checkbox(
                            model.label,
                            value=model.label in project.draft_selected_model_labels,
                            on_change=_on_toggle,
                        )

                        def _remove(lbl=model.label) -> None:
                            state.remove_model(lbl)
                            _refresh_models()

                        ui.button(icon="delete", on_click=_remove).props("flat dense")

        _refresh_models()

        with ui.expansion("Add model"):
            label_input = ui.input("Label (e.g. 'llama3.2:3b (ollama)')")
            provider_select = ui.select(
                ["ollama", "openai_compat"], value="ollama", label="Provider"
            )
            model_input = ui.input("Model name")
            base_url_input = ui.input("Base URL", value="http://localhost:11434")
            api_key_input = ui.input("API Key", password=True)

            def _add_model() -> None:
                if not label_input.value or not model_input.value:
                    ui.notify("Label and model name are required.", type="warning")
                    return
                state.add_model(
                    ModelUnderTest(
                        label=label_input.value,
                        llm_config=LLMConfig(
                            provider=provider_select.value,
                            model=model_input.value,
                            base_url=base_url_input.value,
                            api_key=api_key_input.value or None,
                        ),
                    )
                )
                _refresh_models()

            ui.button("Add", on_click=_add_model)

    with ui.card().classes("w-full"):
        ui.label("Execution").classes("text-md font-bold")
        run_name_input = ui.input(
            "Run name (optional)",
            value=project.draft_run_name,
            on_change=tracked_on_change(state, project, "draft_run_name"),
        ).classes("w-64")
        progress_bar = ui.linear_progress(value=0).classes("w-full")
        status_label = ui.label("Idle")
        progress_table = ui.table(
            columns=[
                {"name": "exercise", "label": "Exercise", "field": "exercise"},
                {"name": "solution", "label": "Solution", "field": "solution"},
                {"name": "model", "label": "Model", "field": "model"},
                {"name": "status", "label": "Status", "field": "status"},
            ],
            rows=[],
            row_key="key",
        ).classes("w-full")
        retry_button = ui.button("Retry", on_click=lambda: state.executor.retry())
        retry_button.set_visibility(False)

        progress_rows: dict[str, dict[str, str]] = {}

        def _on_progress(job: BenchJob, status: str, message, record) -> None:
            key = f"{job.exercise_config.id}:{job.solution.id}:{job.model.label}"
            progress_rows[key] = {
                "key": key,
                "exercise": job.exercise_config.id,
                "solution": job.solution.label or job.solution.id[:8],
                "model": job.model.label,
                "status": status if not message else f"{status} ({message})",
            }
            progress_table.rows = list(progress_rows.values())
            done = sum(
                1
                for r in progress_rows.values()
                if r["status"].startswith(("completed", "failed"))
            )
            progress_bar.value = done / max(len(progress_rows), 1)
            status_label.set_text(status)
            retry_button.set_visibility(status == "paused")
            progress_table.update()

        async def _run_benchmark() -> None:
            if not project.draft_selected_model_labels:
                ui.notify("Select at least one model to test.", type="warning")
                return
            progress_rows.clear()
            progress_table.rows = []
            run, jobs = state.build_run_jobs(name=run_name_input.value)
            if not jobs:
                ui.notify("No (exercise, solution) pairs to run yet.", type="warning")
                return
            status_label.set_text(f"Running '{run.name}'…")
            await state.run_benchmark(jobs, run, _on_progress)
            status_label.set_text(f"'{run.name}': {run.status}")
            ui.notify(f"Benchmark run '{run.name}' {run.status}.", type="positive")
            refresh_run_history.refresh()

        ui.button("Run Benchmark", on_click=_run_benchmark).classes("bg-primary")

    with ui.card().classes("w-full"):
        ui.label("Run History").classes("text-md font-bold")

        @ui.refreshable
        def refresh_run_history() -> None:
            if not project.runs:
                ui.label("No runs yet.").classes("text-caption")
                return
            for run in reversed(project.runs):
                with ui.row().classes("items-center gap-3"):
                    ui.label(run.name).classes("font-bold")
                    ui.badge(run.status)
                    ui.label(f"{run.job_count} jobs").classes("text-caption")
                    ui.label(", ".join(run.model_labels)).classes("text-caption")

        refresh_run_history()
