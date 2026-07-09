"""Exercises tab: browse the exercise catalog and manage student solutions."""

from __future__ import annotations

from collections.abc import Callable

from nicegui import events, ui

from notebook_ta.bench.executor import extended_sys_path, run_setup_code
from notebook_ta.bench.internal_model import InternalModelService
from notebook_ta.bench.models import DEFAULT_TAG_COLOR, StudentSolution
from notebook_ta.bench.state import BenchAppState
from notebook_ta.bench.ui.tag_badges import render_tag_badge
from notebook_ta.config.models import ExerciseConfig, GlobalConfig, PromptConfig
from notebook_ta.exercise.definition import Exercise
from notebook_ta.notebook._ansi import ansi_to_html
from notebook_ta.testing.runner import TestResult, TestRunner


def build(
    state: BenchAppState,
    on_catalog_change: Callable[[], object] | None = None,
) -> Callable[[], None]:
    """Render the Exercises tab and return a callback which refreshes its content."""
    container = ui.column().classes("w-full")

    def render_all() -> None:
        container.clear()
        with container:
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Exercises").classes("text-lg font-bold")
                _build_add_exercise_dialog(state, render_all, on_catalog_change)
            if not state.exercise_registry:
                ui.label(
                    "No exercise catalog is loaded. Create a project from an exercises TOML file."
                ).classes("text-caption")
                return
            for exercise_id, config in state.exercise_registry.items():
                expansion = ui.expansion(
                    config.name or exercise_id,
                    caption=exercise_id if config.name else None,
                    value=True,
                ).classes("w-full")
                with expansion:

                    def _on_exercise_name_change(
                        event: events.ValueChangeEventArguments[str | None],
                        exercise_config: ExerciseConfig = config,
                        exercise_expansion: ui.expansion = expansion,
                    ) -> None:
                        name = event.value or ""
                        try:
                            state.update_exercise_name(exercise_config.id, name)
                        except Exception as exc:
                            ui.notify(f"Could not rename exercise: {exc}", type="negative")
                            return
                        exercise_expansion.set_text(name.strip() or exercise_config.id)
                        if on_catalog_change:
                            on_catalog_change()

                    ui.input(
                        "Exercise name",
                        value=config.name or "",
                        on_change=_on_exercise_name_change,
                    ).props("debounce=500").classes("w-full max-w-xl")
                    _build_setup_code_dialog(state, config, on_catalog_change)
                    with ui.card().classes("w-full bg-grey-1"):
                        ui.markdown(config.statement or "*(no statement)*")
                    _build_solutions(state, config, on_catalog_change)

    render_all()
    return render_all


def _build_solutions(
    state: BenchAppState,
    config: ExerciseConfig,
    on_solution_change: Callable[[], object] | None = None,
) -> None:
    """Render solution cards side by side with horizontal overflow."""

    @ui.refreshable
    def render_solutions() -> None:
        solutions = state.project.solutions_for(config.id)
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(f"Student solutions ({len(solutions)})").classes("text-sm font-bold")
            with ui.row().classes("items-center gap-2"):

                def _add_blank() -> None:
                    state.add_solution(config.id)
                    render_solutions.refresh()
                    if on_solution_change:
                        on_solution_change()

                ui.button("Add blank solution", on_click=_run_once(_add_blank))
                _build_generate_dialog(
                    state,
                    config,
                    render_solutions.refresh,
                    on_solution_change,
                )

        if not solutions:
            ui.label("No student solutions yet.").classes("text-caption")
            return

        with (
            ui.element("div")
            .classes("w-full max-w-full overflow-x-auto pb-2")
            .style("min-width: 0; max-width: calc(100vw - 6rem)"),
            ui.row().classes("w-max flex-nowrap items-stretch gap-4"),
        ):
            for solution in solutions:
                with ui.card().classes("shrink-0").style(
                    "width: 28rem; min-width: 28rem; max-width: 28rem"
                ):

                    def _on_label_change(
                        event: events.ValueChangeEventArguments[str | None],
                        sol: StudentSolution = solution,
                    ) -> None:
                        state.update_solution_label(sol.id, event.value or "")
                        if on_solution_change:
                            on_solution_change()

                    ui.input(
                        "Solution name",
                        value=solution.label,
                        placeholder=solution.id[:8],
                        on_change=_on_label_change,
                    ).props("debounce=500").classes("w-full")

                    def _on_code_change(
                        event: events.ValueChangeEventArguments[str],
                        sol: StudentSolution = solution,
                    ) -> None:
                        sol.code = event.value
                        state.mark_dirty()

                    ui.codemirror(
                        value=solution.code, language="Python", on_change=_on_code_change
                    ).classes("w-full").style("min-height: 200px")

                    tags_select = ui.select(
                        options=list(state.project.settings.known_tags),
                        value=list(solution.tags),
                        label="Tags",
                        multiple=True,
                        with_input=True,
                        new_value_mode="add-unique",
                    ).classes("w-full")
                    tag_badges = ui.row().classes("gap-1")

                    def _refresh_tag_badges(
                        sol: StudentSolution = solution,
                        container: ui.row = tag_badges,
                    ) -> None:
                        container.clear()
                        with container:
                            for tag in sol.tags:
                                render_tag_badge(state.project.settings, tag)

                    def _on_tags_change(
                        event: events.ValueChangeEventArguments[list[str] | None],
                        sol: StudentSolution = solution,
                        refresh_badges: Callable[[], None] = _refresh_tag_badges,
                    ) -> None:
                        new_tags = list(event.value or [])
                        sol.tags = new_tags
                        for tag in new_tags:
                            if tag not in state.project.settings.known_tags:
                                state.project.settings.known_tags.append(tag)
                                state.project.settings.tag_colors[tag] = DEFAULT_TAG_COLOR
                        state.mark_dirty()
                        refresh_badges()

                    tags_select.on_value_change(_on_tags_change)
                    _refresh_tag_badges()

                    result_area = ui.column()

                    def _run_tests(
                        sol: StudentSolution = solution,
                        exercise_config: ExerciseConfig = config,
                        results: ui.element = result_area,
                    ) -> None:
                        _run_solution_tests(state, exercise_config, sol, results)

                    def _remove(sol: StudentSolution = solution) -> None:
                        state.remove_solution(sol.id)
                        render_solutions.refresh()
                        if on_solution_change:
                            on_solution_change()

                    with ui.row():
                        ui.button("Run tests", on_click=_drop_queued_duplicates(_run_tests))
                        ui.button("Remove", on_click=_run_once(_remove)).props(
                            "flat color=negative"
                        )

    render_solutions()


def _build_add_exercise_dialog(
    state: BenchAppState,
    refresh_exercises: Callable[[], None],
    on_catalog_change: Callable[[], object] | None,
) -> None:
    """Build the dialog used to append a new exercise to the local catalog."""
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl"):
        ui.label("Add exercise").classes("text-lg font-bold")
        exercise_id = ui.input("Exercise ID").classes("w-full")
        exercise_name = ui.input("New exercise name").classes("w-full")
        statement = ui.textarea("Statement").classes("w-full")

        def _add() -> None:
            try:
                state.add_exercise(
                    exercise_id.value or "",
                    exercise_name.value or "",
                    statement.value or "",
                )
            except Exception as exc:
                ui.notify(f"Could not add exercise: {exc}", type="negative")
                return
            dialog.close()
            refresh_exercises()
            if on_catalog_change:
                on_catalog_change()
            ui.notify("Exercise added.", type="positive")

        with ui.row():
            ui.button("Create exercise", on_click=_add)
            ui.button("Cancel", on_click=dialog.close).props("flat")

    ui.button("Add exercise", icon="add", on_click=dialog.open)


def _build_setup_code_dialog(
    state: BenchAppState,
    config: ExerciseConfig,
    on_catalog_change: Callable[[], object] | None,
) -> None:
    """Build the dialog used to edit exercise setup code."""
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-3xl"):
        ui.label(f"Setup code for {config.id}").classes("text-lg font-bold")
        setup_editor = ui.codemirror(
            value=state.project.setup_code_for(config.id), language="Python"
        ).classes("w-full").style("min-height: 260px")

        def _save() -> None:
            try:
                state.update_exercise_setup_code(config.id, setup_editor.value or "")
            except Exception as exc:
                ui.notify(f"Could not save setup code: {exc}", type="negative")
                return
            dialog.close()
            if on_catalog_change:
                on_catalog_change()
            ui.notify("Setup code saved.", type="positive")

        with ui.row():
            ui.button("Save setup code", on_click=_save)
            ui.button("Cancel", on_click=dialog.close).props("flat")

    label = "Edit setup code" if state.project.setup_code_for(config.id) else "Add setup code"
    ui.button(label, icon="code", on_click=dialog.open).props("outline")


def _run_once(action: Callable[[], None]) -> Callable[[], None]:
    """Return a handler that ignores duplicate invocations after one successful call."""
    called = False

    def handler() -> None:
        nonlocal called
        if called:
            return
        called = True
        try:
            action()
        except Exception:
            called = False
            raise

    return handler


def _drop_queued_duplicates(action: Callable[[], None]) -> Callable[[], None]:
    """Return a handler that ignores duplicate events queued by the same UI gesture."""
    running_or_queued = False

    def _reset() -> None:
        nonlocal running_or_queued
        running_or_queued = False

    def handler() -> None:
        nonlocal running_or_queued
        if running_or_queued:
            return
        running_or_queued = True
        try:
            action()
        except Exception:
            _reset()
            raise
        ui.timer(0.2, _reset, once=True)

    return handler


def _run_solution_tests(
    state: BenchAppState,
    exercise_config: ExerciseConfig,
    solution: StudentSolution,
    results: ui.element,
) -> None:
    """Exec the solution and run its unit tests, rendering results into `results`."""
    error: str | None = None
    test_results: list[TestResult] = []
    try:
        namespace: dict[str, object] = {}
        with extended_sys_path(state.project.settings.python_path_dirs):
            exec(solution.code, namespace)  # noqa: S102 -- isolated authoring-time sandbox
            global_config = GlobalConfig(
                llm=state.project.settings.internal_model,
                prompts=PromptConfig(on_success="", on_failure="", on_no_llm=""),
            )
            exercise = Exercise(exercise_config, global_config)
            test_names = [test_def.name for test_def in exercise.tests]
            setup_results = run_setup_code(
                state.project.setup_code_for(exercise_config.id),
                namespace,
                test_names,
            )
            if setup_results is None:
                test_results = TestRunner().run(exercise, namespace)
            else:
                test_results = setup_results
    except Exception as exc:  # pragma: no cover - defensive UI feedback
        error = str(exc)

    results.clear()
    with results:
        if error:
            ui.label(f"Error: {error}").classes("text-negative")
        else:
            if not test_results:
                ui.label("No unit tests are configured for this exercise.").classes(
                    "text-caption text-grey-7"
                )
                return
            for result in test_results:
                icon = "check_circle" if result.passed else "cancel"
                color = "positive" if result.passed else "negative"
                with ui.row().classes("items-center gap-1"):
                    ui.icon(icon).classes(f"text-{color}")
                    ui.label(result.name)
                    if result.message:
                        ui.html(
                            f'<div style="white-space: pre-wrap; font-family: monospace">'
                            f"— {ansi_to_html(result.message)}</div>"
                        ).classes("text-caption")


def _build_generate_dialog(
    state: BenchAppState,
    config: ExerciseConfig,
    refresh_solutions: Callable[[], object],
    on_solution_change: Callable[[], object] | None = None,
) -> None:
    """Build the "Generate with internal model" dialog for one exercise."""
    with ui.dialog() as dialog, ui.card().classes("w-full"):
        ui.label(f"Generate a draft solution for {config.id}")
        tags_select = ui.select(
            options=list(state.project.settings.known_tags),
            label="Tags",
            multiple=True,
            with_input=True,
            new_value_mode="add-unique",
        ).classes("w-full")
        with ui.row().classes("gap-1"):
            for tag in state.project.settings.known_tags:
                render_tag_badge(state.project.settings, tag)
        preview = ui.markdown("")

        with ui.row().classes("items-center gap-2"):
            spinner = ui.spinner(size="lg")
            spinner.set_visibility(False)
            working_label = ui.label("Generating…")
            working_label.set_visibility(False)

        async def _generate() -> None:
            tags = list(tags_select.value or [])
            for tag in tags:
                if tag not in state.project.settings.known_tags:
                    state.project.settings.known_tags.append(tag)
                    state.project.settings.tag_colors[tag] = DEFAULT_TAG_COLOR

            generate_button.disable()
            cancel_button.disable()
            spinner.set_visibility(True)
            working_label.set_visibility(True)
            preview.set_content("")
            try:
                service = InternalModelService(state.project.settings)
                accumulated = ""
                async for chunk in service.generate_solution(config, tags):
                    accumulated += chunk
                    preview.set_content(f"```python\n{accumulated}\n```")
                state.add_solution(
                    config.id, code=accumulated, tags=tags, generated_by_internal_model=True
                )
                refresh_solutions()
                if on_solution_change:
                    on_solution_change()
                dialog.close()
            except Exception as exc:
                ui.notify(f"Generation failed: {exc}", type="negative")
            finally:
                spinner.set_visibility(False)
                working_label.set_visibility(False)
                generate_button.enable()
                cancel_button.enable()

        with ui.row():
            generate_button = ui.button("Generate", on_click=_generate)
            cancel_button = ui.button("Cancel", on_click=dialog.close)

    ui.button("Generate with internal model", on_click=dialog.open)
