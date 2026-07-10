"""notebook-ta public API."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any, cast

import nest_asyncio

from notebook_ta.config.loader import load_exercises, load_global
from notebook_ta.config.models import ConfigurationError, GlobalConfig, LLMConfig
from notebook_ta.exercise.definition import Exercise
from notebook_ta.i18n import set_language, translate
from notebook_ta.exercise.registry import ExerciseRegistry
from notebook_ta.llm.base import LLMProvider, create_provider
from notebook_ta.logging import get_logger, setup_logging
from notebook_ta.notebook.extractor import detect_notebook_path, extract_statements
from notebook_ta.notebook.magic import load_ipython_extension
from notebook_ta.notebook.session import SessionState

# Module-level singletons updated on each call to load()
_registry: ExerciseRegistry = ExerciseRegistry()
_llm_provider: LLMProvider | None = None
_global_config: GlobalConfig | None = None

_log = get_logger("init")


def load(
    global_config: str | Path,
    exercises_config: str | Path,
    *,
    notebook_path: str | Path | None = None,
    llm_overrides: dict[str, Any] | None = None,
    debug: bool = False,
) -> None:
    """Load configuration files, register exercises, run auto-setup if needed,
    and register the %%notebook_ta IPython magic.

    Must be called from within a Jupyter notebook cell.

    Args:
        global_config: Path or URL to the global configuration TOML.
        exercises_config: Path or URL to the exercises TOML.
        notebook_path: Optional path to the ``.ipynb`` file.  Required only
            when one or more exercises omit ``statement`` from the TOML and
            the statement should instead be extracted from the notebook's
            markdown cells (``<div id="<exercise_id>">…</div>`` pattern).  If
            not provided the system will try to detect the notebook path
            automatically; pass this argument explicitly when auto-detection
            fails.
        llm_overrides: Optional dict of LLM settings that override the values
            from *global_config*. Valid keys mirror :class:`LLMConfig` fields
            (e.g. ``model``, ``base_url``, ``provider``, ``timeout``).
        debug: When ``True``, enable DEBUG-level logging to the terminal and
               display the final LLM prompt in the notebook output as a
               collapsible widget before each LLM call.  Defaults to ``False``.
    """
    global _registry, _llm_provider, _global_config

    # Allow asyncio event loop nesting required in Jupyter environments
    nest_asyncio.apply()

    # Configure logging before anything else so all subsequent calls are captured.
    setup_logging(debug=debug)

    # 1. Load and validate configuration
    _log.info("Loading notebook-ta configuration")
    cfg = load_global(global_config)
    set_language(cfg.language)
    exercise_configs = load_exercises(exercises_config)

    # 1b. Apply programmatic LLM overrides (validated through Pydantic)
    if llm_overrides:
        try:
            updated_llm = LLMConfig.model_validate({**cfg.llm.model_dump(), **llm_overrides})
        except Exception as exc:
            raise ConfigurationError(f"Invalid LLM override: {exc}") from exc
        cfg = cfg.model_copy(update={"llm": updated_llm})

    # 2. Auto-setup wizard
    if cfg.llm.model == "auto":
        _run_setup_wizard(cfg)

    # 3. Create LLM provider
    provider = create_provider(cfg.llm)
    _log.info("LLM provider created: %r (model=%r)", cfg.llm.provider, cfg.llm.model)

    # 4. Resolve missing statements from the notebook file
    missing = [ex for ex in exercise_configs if ex.statement is None]
    if missing:
        nb_path = Path(notebook_path) if notebook_path is not None else _resolve_notebook_path()
        _log.info("Extracting %d statement(s) from notebook: %s", len(missing), nb_path)
        extracted = extract_statements(nb_path)
        for ex_cfg in missing:
            text = extracted.get(ex_cfg.id)
            if text is None:
                raise ConfigurationError(
                    f"Exercise {ex_cfg.id!r} has no statement in the TOML and no "
                    f"<div id={ex_cfg.id!r}> was found in {nb_path}."
                )
            ex_cfg.statement = text

    # 5. Build and populate the registry
    registry = ExerciseRegistry()
    for ex_cfg in exercise_configs:
        registry.register(Exercise(config=ex_cfg, global_config=cfg))

    session = SessionState(hint_history_length=cfg.prompts.hint_history_length)
    _log.info("Registry populated: %d exercise(s)", len(exercise_configs))

    # 6. Register the IPython magic
    try:
        from IPython import get_ipython  # type: ignore[attr-defined]

        ip = get_ipython()  # type: ignore[no-untyped-call]
        if ip is not None:
            load_ipython_extension(
                ip, registry=registry, llm_provider=provider, session=session, debug=debug
            )
        else:
            import warnings

            warnings.warn(
                "notebook_ta.load() was called outside of an IPython/Jupyter environment. "
                "The %%notebook_ta magic will not be registered.",
                stacklevel=2,
            )
    except ImportError:
        import warnings

        warnings.warn(
            "IPython is not installed. The %%notebook_ta magic will not be registered.",
            stacklevel=2,
        )

    # Update module singletons
    _registry = registry
    _llm_provider = provider
    _global_config = cfg
    _log.info("notebook-ta loaded successfully")

    from IPython import display as ipydisplay

    with contextlib.suppress(Exception):
        cast(Any, ipydisplay.display)(
            cast(Any, ipydisplay.Markdown)(
                translate(
                    "load_success",
                    {
                        "provider": cfg.llm.provider,
                        "model": cfg.llm.model,
                        "exercise_count": len(exercise_configs),
                    },
                )
            )
        )


def get_registry() -> ExerciseRegistry:
    """Return the active ExerciseRegistry for introspection."""
    return _registry


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_notebook_path() -> Path:
    """Auto-detect the current notebook path or raise ConfigurationError."""
    try:
        from IPython import get_ipython as _gip  # type: ignore[attr-defined]

        ip = _gip()  # type: ignore[no-untyped-call]
    except ImportError:
        ip = None

    path = detect_notebook_path(ip)
    if path is None:
        raise ConfigurationError(
            "Could not automatically determine the notebook path. "
            "Pass notebook_path= to notebook_ta.load() explicitly, e.g.:\n"
            "  notebook_ta.load(global_cfg, exercises_cfg, "
            "notebook_path='my_notebook.ipynb')"
        )
    return path


def _run_setup_wizard(cfg: GlobalConfig) -> None:
    """Run hardware detection and update cfg.llm.model in place."""
    from notebook_ta.setup_wizard.detector import detect_hardware, select_model

    profile = detect_hardware()
    model_spec = select_model(cfg.llm.available_models, profile)

    try:
        from IPython import display as ipydisplay

        if model_spec is not None:
            cfg.llm.model = model_spec.name
            gpu_text = (
                translate(
                    "hardware_gpu_text",
                    {"gpu_name": profile.gpu_name, "vram_gb": profile.vram_gb},
                )
                if profile.gpu_name
                else ""
            )
            cast(Any, ipydisplay.display)(
                cast(Any, ipydisplay.Markdown)(
                    translate(
                        "hardware_detected",
                        {
                            "ram_gb": profile.ram_gb,
                            "gpu_text": gpu_text,
                            "model_name": model_spec.name,
                            "model_description": model_spec.description,
                        },
                    )
                )
            )
        else:
            gpu_text = (
                translate(
                    "hardware_gpu_text",
                    {"gpu_name": profile.gpu_name, "vram_gb": profile.vram_gb},
                )
                if profile.gpu_name
                else ""
            )
            cast(Any, ipydisplay.display)(
                cast(Any, ipydisplay.Markdown)(
                    translate("hardware_no_model", {"ram_gb": profile.ram_gb, "gpu_text": gpu_text})
                )
            )
    except Exception:
        if model_spec is not None:
            cfg.llm.model = model_spec.name
