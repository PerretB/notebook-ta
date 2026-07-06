"""Compare tab: matrix of benchmark results across models and prompt versions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from statistics import mean

from nicegui import events, ui

from notebook_ta.bench.hashing import is_stale
from notebook_ta.bench.models import (
    BenchmarkRun,
    BenchProject,
    ExecutionRecord,
    StudentSolution,
)
from notebook_ta.bench.state import BenchAppState
from notebook_ta.bench.ui.tag_badges import render_tag_badge
from notebook_ta.config.models import ExerciseConfig

Combination = tuple[str, str]


@dataclass(frozen=True)
class _AggregateMetrics:
    """Average performance values for a visible comparison column."""

    ttft_s: float | None
    total_s: float | None
    throughput_tokens_per_s: float | None


def build(state: BenchAppState) -> Callable[[], object]:
    """Render the Compare tab and return a callback which refreshes the matrix."""
    container = ui.column().classes("w-full")
    selected_combinations: list[Combination] | None = None
    selected_tags: list[str] = []

    @ui.refreshable
    def render() -> None:
        nonlocal selected_combinations, selected_tags
        project = state.project
        combinations = _all_combinations(project)
        available = set(combinations)
        if selected_combinations is None:
            selected_combinations = _default_combinations(project, combinations)
        else:
            selected_combinations = [c for c in selected_combinations if c in available]
        selected_tags = [tag for tag in selected_tags if tag in project.settings.known_tags]

        option_to_combination = {
            f"combination-{index}": combination for index, combination in enumerate(combinations)
        }
        combination_to_option = {
            combination: option for option, combination in option_to_combination.items()
        }

        container.clear()
        with container:
            with ui.row().classes("w-full items-start gap-4"):
                combination_select = ui.select(
                    options={
                        option: _combination_label(project, combination)
                        for option, combination in option_to_combination.items()
                    },
                    value=[
                        combination_to_option[c]
                        for c in selected_combinations
                        if c in combination_to_option
                    ],
                    multiple=True,
                    label="Model / prompt versions to compare",
                ).classes("grow min-w-80")

                tag_select = ui.select(
                    options=project.settings.known_tags,
                    value=selected_tags,
                    multiple=True,
                    label="Filter solutions by tags",
                ).classes("min-w-64")

                run_select = ui.select(
                    options={run.id: _run_label(run) for run in reversed(project.runs)},
                    label="Run to delete",
                ).classes("min-w-64")

                def _request_run_deletion() -> None:
                    run = next(
                        (
                            candidate
                            for candidate in project.runs
                            if candidate.id == run_select.value
                        ),
                        None,
                    )
                    if run is None:
                        ui.notify("Select a run to delete.", type="warning")
                        return
                    _open_delete_run_dialog(state, run, render.refresh)

                ui.button("Delete run", icon="delete", on_click=_request_run_deletion).props(
                    "outline color=negative"
                )

            def _select_combinations(
                event: events.ValueChangeEventArguments[list[str] | None],
            ) -> None:
                nonlocal selected_combinations
                selected_combinations = [
                    option_to_combination[key]
                    for key in event.value or []
                    if key in option_to_combination
                ]
                render.refresh()

            def _select_tags(
                event: events.ValueChangeEventArguments[list[str] | None],
            ) -> None:
                nonlocal selected_tags
                selected_tags = list(event.value or [])
                render.refresh()

            combination_select.on_value_change(_select_combinations)
            tag_select.on_value_change(_select_tags)

            if not state.exercise_registry:
                ui.label("No exercise catalog loaded.").classes("text-caption")
                return
            if not combinations:
                ui.label("No benchmark results are available yet.").classes("text-caption")
                return
            if not selected_combinations:
                ui.label("Select at least one model / prompt version to compare.").classes(
                    "text-caption"
                )
                return

            exercise_rows: list[tuple[ExerciseConfig, list[StudentSolution]]] = []
            for exercise_id, config in state.exercise_registry.items():
                solutions = project.solutions_for(exercise_id)
                if selected_tags:
                    solutions = [
                        solution
                        for solution in solutions
                        if all(tag in solution.tags for tag in selected_tags)
                    ]
                if not solutions:
                    continue
                exercise_rows.append((config, solutions))

            aggregates = {
                combination: _aggregate_metrics(
                    _visible_records(project, exercise_rows, combination)
                )
                for combination in selected_combinations
            }
            for config, solutions in exercise_rows:
                with ui.expansion(
                    config.name or config.id,
                    caption=config.id if config.name else None,
                    value=True,
                ).classes("w-full"):
                    _render_exercise_matrix(
                        state,
                        config,
                        solutions,
                        selected_combinations,
                        aggregates,
                        render.refresh,
                    )

            if not exercise_rows:
                ui.label("No solutions match the selected tags.").classes("text-caption")

    render()
    return render.refresh


def _all_combinations(project: BenchProject) -> list[Combination]:
    """Return all model/prompt combinations in first-execution order."""
    combinations: dict[Combination, None] = {}
    for record in project.execution_records:
        combinations[(record.model_label, record.prompt_version_id)] = None
    return list(combinations)


def _default_combinations(
    project: BenchProject, combinations: list[Combination]
) -> list[Combination]:
    """Return combinations from the most recent run which produced saved results."""
    available = set(combinations)
    for run in reversed(project.runs):
        defaults = [
            (model_label, run.prompt_version_id)
            for model_label in run.model_labels
            if (model_label, run.prompt_version_id) in available
        ]
        if defaults:
            return defaults
    return combinations[-1:]


def _combination_label(project: BenchProject, combination: Combination) -> str:
    """Build a selector/header label containing model, prompt version, and timestamp."""
    model_label, prompt_version_id = combination
    prompt = next((p for p in project.prompt_versions if p.id == prompt_version_id), None)
    if prompt is None:
        return f"{model_label} / {prompt_version_id}"
    timestamp = prompt.created_at.strftime("%Y-%m-%d %H:%M UTC")
    return f"{model_label} / {prompt_version_id} / {timestamp}"


def _run_label(run: BenchmarkRun) -> str:
    """Return a concise label for a run-deletion selector."""
    timestamp = run.started_at.strftime("%Y-%m-%d %H:%M UTC")
    return f"{run.name or run.id[:8]} / {timestamp}"


def _visible_records(
    project: BenchProject,
    exercise_rows: list[tuple[ExerciseConfig, list[StudentSolution]]],
    combination: Combination,
) -> list[ExecutionRecord]:
    """Return latest records represented by one currently visible matrix column."""
    model_label, prompt_version_id = combination
    records: list[ExecutionRecord] = []
    for config, solutions in exercise_rows:
        for solution in solutions:
            record = project.latest_record(
                config.id, solution.id, model_label, prompt_version_id
            )
            if record is not None:
                records.append(record)
    return records


def _aggregate_metrics(records: list[ExecutionRecord]) -> _AggregateMetrics:
    """Average available TTFT, total-time, and throughput metrics in ``records``."""
    ttfts = [
        value
        for record in records
        if (value := record.metrics.time_to_first_token_s) is not None
    ]
    totals = [record.metrics.total_generation_time_s for record in records]
    throughputs = [
        value
        for record in records
        if (value := record.metrics.throughput_tokens_per_s) is not None
    ]
    return _AggregateMetrics(
        ttft_s=mean(ttfts) if ttfts else None,
        total_s=mean(totals) if totals else None,
        throughput_tokens_per_s=mean(throughputs) if throughputs else None,
    )


def _render_exercise_matrix(
    state: BenchAppState,
    config: ExerciseConfig,
    solutions: list[StudentSolution],
    combinations: list[Combination],
    aggregates: dict[Combination, _AggregateMetrics],
    refresh_matrix: Callable[[], object],
) -> None:
    """Render one collapsible exercise group as aligned matrix rows and columns."""
    project = state.project
    minimum_width = 14 + 22 * len(combinations)
    grid_style = (
        "grid-template-columns: minmax(14rem, 0.65fr) "
        f"repeat({len(combinations)}, minmax(22rem, 1fr)); "
        f"min-width: {minimum_width}rem"
    )

    with (
        ui.element("div").classes("w-full overflow-x-auto pb-2"),
        ui.element("div").classes("grid gap-3 items-stretch").style(grid_style),
    ):
        with ui.card().classes("p-3 bg-grey-2 rounded"):
            ui.label("Exercise / student solution").classes("font-bold")
            ui.button(
                "View exercise statement",
                icon="description",
                on_click=lambda: _open_exercise_statement(config),
            ).props("flat dense")
        for combination in combinations:
            aggregate = aggregates[combination]
            with ui.card().classes("p-3 bg-primary text-white rounded"):
                ui.label(_combination_label(project, combination)).classes("font-bold")
                with ui.row().classes("gap-2"):
                    ui.badge(_average_label("TTFT", aggregate.ttft_s, "s"))
                    ui.badge(_average_label("Total", aggregate.total_s, "s"))
                    ui.badge(
                        _average_label(
                            "Speed", aggregate.throughput_tokens_per_s, "tok/s"
                        )
                    )

        for solution in solutions:
            with ui.card().classes("h-full bg-grey-1"):
                ui.label(solution.label or solution.id[:8]).classes("font-bold")
                ui.code(solution.code or "# Empty solution").classes(
                    "w-full max-h-64 overflow-auto"
                )
                if solution.tags:
                    with ui.row().classes("gap-1"):
                        for tag in solution.tags:
                            render_tag_badge(project.settings, tag)

            for model_label, prompt_version_id in combinations:
                record = project.latest_record(
                    config.id,
                    solution.id,
                    model_label,
                    prompt_version_id,
                )
                if record is None:
                    with ui.card().classes("h-full bg-grey-1"):
                        ui.label("No result for this configuration.").classes(
                            "text-caption text-grey-7"
                        )
                    continue
                _render_result_cell(
                    state,
                    config,
                    solution,
                    record,
                    is_stale(record, config, solution),
                    refresh_matrix,
                )


def _average_label(name: str, value: float | None, unit: str) -> str:
    """Format an aggregate metric badge label."""
    if value is None:
        return f"Avg {name}: n/a"
    separator = " " if "/" in unit else ""
    return f"Avg {name}: {value:.2f}{separator}{unit}"


def _open_exercise_statement(config: ExerciseConfig) -> None:
    """Open a modal containing the complete exercise statement."""
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-3xl"):
        ui.label(config.name or config.id).classes("text-lg font-bold")
        ui.markdown(config.statement or "No exercise statement is available.").classes("w-full")
        ui.button("Close", on_click=dialog.close)
    dialog.open()


def _open_delete_run_dialog(
    state: BenchAppState,
    run: BenchmarkRun,
    refresh_matrix: Callable[[], object],
) -> None:
    """Ask for explicit confirmation before permanently deleting a run."""
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
        ui.label(f"Delete run '{run.name or run.id[:8]}'?").classes("text-lg font-bold")
        ui.label(
            "This will permanently delete the run and all of its results. "
            "This cannot be undone."
        ).classes("text-negative")

        def _delete() -> None:
            deleted = state.delete_run(run.id)
            dialog.close()
            if deleted:
                ui.notify("Run deleted.", type="positive")
                refresh_matrix()
            else:
                ui.notify("The run was already deleted.", type="warning")

        with ui.row().classes("justify-end w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Delete permanently", on_click=_delete).props("color=negative")
    dialog.open()


def _render_result_cell(
    state: BenchAppState,
    config: ExerciseConfig,
    solution: StudentSolution,
    record: ExecutionRecord,
    stale: bool,
    refresh_matrix: Callable[[], object],
) -> None:
    """Render one interactive result cell in the comparison matrix."""
    cell_classes = "h-full cursor-pointer"
    if stale:
        cell_classes += " opacity-50 bg-grey-3"

    def _open_details() -> None:
        _open_details_dialog(record)

    with ui.card().classes(cell_classes).on("click", _open_details):
        if stale:
            ui.label("⚠️ Stale (Inputs Modified)").classes("text-warning font-bold")

        with ui.row().classes("gap-2"):
            ttft = record.metrics.time_to_first_token_s
            ui.badge(f"TTFT: {ttft:.2f}s" if ttft is not None else "TTFT: n/a")
            ui.badge(f"Total: {record.metrics.total_generation_time_s:.2f}s")
            throughput = record.metrics.throughput_tokens_per_s
            ui.badge(f"{throughput:.1f} tok/s" if throughput is not None else "Speed: n/a")

        if record.status == "failed":
            ui.label(f"Error: {record.error or 'Generation failed'}").classes("text-negative")
        else:
            ui.markdown(record.llm_output).classes("w-full")

        with ui.row().classes("items-center justify-between w-full"):
            ui.label("Click cell for details").classes("text-caption text-grey-7")
            if stale:

                async def _rerun() -> None:
                    do_rerun = state.rerun_job(
                        config.id,
                        solution.id,
                        record.model_label,
                        record.prompt_version_id,
                    )
                    await do_rerun()
                    ui.notify("Re-run complete.", type="positive")
                    refresh_matrix()

                ui.button("Re-run").props("flat dense").on("click.stop", _rerun)


def _open_details_dialog(record: ExecutionRecord) -> None:
    """Open the detailed prompt, tests, metrics, and errors for one matrix cell."""
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-5xl"):
        ui.label(f"{record.model_label} — {record.prompt_version_id}").classes("text-lg font-bold")
        ui.label("Full Prompt").classes("font-bold")
        ui.code(record.full_prompt).classes("w-full max-h-80 overflow-auto")

        ui.label("Unit Test Results").classes("font-bold")
        if record.test_results:
            for result in record.test_results:
                icon = "✅" if result.passed else "❌"
                ui.label(f"{icon} {result.name}: {result.message or ''}")
        else:
            ui.label("No unit test results recorded.").classes("text-caption")

        ui.label("Performance Metrics").classes("font-bold")
        with ui.row().classes("gap-3"):
            ttft = record.metrics.time_to_first_token_s
            ui.label(f"TTFT: {ttft:.3f}s" if ttft is not None else "TTFT: n/a")
            ui.label(f"Total: {record.metrics.total_generation_time_s:.3f}s")
            throughput = record.metrics.throughput_tokens_per_s
            ui.label(
                f"Throughput: {throughput:.2f} tok/s"
                if throughput is not None
                else "Throughput: n/a"
            )
            usage = record.metrics.token_usage
            ui.label(f"Prompt tokens: {usage.prompt_tokens or 'n/a'}")
            ui.label(f"Completion tokens: {usage.completion_tokens or 'n/a'}")

        if record.error:
            ui.label(f"Error: {record.error}").classes("text-negative")
        ui.button("Close", on_click=dialog.close)
    dialog.open()
