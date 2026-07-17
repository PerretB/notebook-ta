"""Internationalized user-facing messages for notebook-ta."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from notebook_ta.logging import get_logger

DEFAULT_LANGUAGE = "en"

_log = get_logger("i18n")

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "debug_prompt_title": "Debug - LLM Prompt ({call_type})",
        "display_busy": (
            "**notebook-ta is already working.**\n\n"
            "Please wait for the current notebook-ta cell or hint request to finish, "
            "then try again."
        ),
        "display_hints_busy_status": (
            "notebook-ta is already working. Try again when the current cell finishes."
        ),
        "display_hints_busy_button": "Computing... please wait",
        "display_hints_button": "Give me hints",
        "display_hints_fetching": "Fetching hints...",
        "display_execution_failure_heading": "Code execution failed",
        "display_execution_failure_detail": (
            "Tests and LLM analysis were not run. Fix the error and run the cell again."
        ),
        "display_hints_tooltip": "Ask the LLM for targeted hints",
        "display_llm_answer_prefix": "🤖",
        "display_llm_unavailable_heading": "LLM unavailable",
        "display_success": "**✅ All tests passed!** Generating analysis...",
        "display_test_results_heading": "Test Results",
        "display_unavailable": (
            "**Exercise `{exercise_id}` not found.**\n\n"
            "Please check the exercise ID in the magic line and ensure "
            "`notebook_ta.load()` has been called with the correct exercises file."
        ),
        "hardware_detected": (
            "**💻 notebook-ta Hardware detected** - auto-selecting LLM model:\n\n"
            "- RAM: {ram_gb:.1f} GB{gpu_text}\n"
            "- **Selected model:** `{model_name}` - {model_description}"
        ),
        "hardware_gpu_text": ", GPU: {gpu_name} ({vram_gb:.1f} GB VRAM)",
        "hardware_no_model": (
            "**💻 notebook-ta Hardware auto-detection:** No suitable model found for your hardware.\n\n"
            "- RAM: {ram_gb:.1f} GB{gpu_text}\n\n"
            "The LLM provider will be marked as unavailable. Please configure a model "
            "manually in your `global_config.toml`."
        ),
        "initialization_title": "notebook-ta initialization",
        "initialization_gpu": ", GPU: {gpu_name} ({vram_gb:.1f} GB VRAM)",
        "initialization_hardware": (
            "💻 Hardware detected: {ram_gb:.1f} GB RAM{gpu_text}. "
            "Selected model: <code>{model_name}</code> — {model_description}"
        ),
        "initialization_no_model": (
            "⚠️ Hardware detected: {ram_gb:.1f} GB RAM{gpu_text}. "
            "No suitable model was found."
        ),
        "initialization_loaded": (
            "✅ notebook-ta loaded — provider: <code>{provider}</code>, "
            "model: <code>{model}</code>, {exercise_count} exercise(s) registered."
        ),
        "load_success": (
            "**✅ notebook-ta loaded.**  Provider: `{provider}` - Model: `{model}`  \n"
            "{exercise_count} exercise(s) registered."
        ),
        "ollama_setup_checking_server": "Checking the local Ollama server…",
        "ollama_setup_starting_server": "Ollama is not running — starting the server…",
        "ollama_setup_server_failed": (
            "❌ The local Ollama server could not be started. "
            "LLM feedback will remain unavailable."
        ),
        "ollama_setup_checking_model": "Checking the selected Ollama model…",
        "ollama_setup_pulling_model": "Downloading the selected Ollama model…",
        "ollama_setup_model_failed": (
            "❌ The selected Ollama model could not be downloaded. "
            "LLM feedback will remain unavailable."
        ),
        "ollama_setup_ready": "✅ Local Ollama server and model are ready.",
        "runner_inline_function_missing": (
            "Function {function_name!r} not found in inline test code for {test_name!r}."
        ),
        "runner_inline_multiple_callables": (
            "Multiple callables in inline test code for {test_name!r}; specify "
            "'function' to disambiguate. Found: {callables}"
        ),
        "runner_inline_no_callable": "No callable found in inline test code for {test_name!r}.",
        "runner_missing_student_name": (
            "Name {name!r} is not defined in the student's namespace. Make sure the "
            "student defines it before running the tests."
        ),
        "runner_output_label": "Output",
        "runner_prepare_timeout_failed": (
            "Could not prepare unit test for timeout enforcement: {error}"
        ),
        "runner_process_no_result": "Unit test process exited without returning a result.",
        "runner_student_globals_not_configured": (
            "The test requests 'student_globals', but its configuration does not specify "
            "'student_symbols' or enable 'export_student_globals'."
        ),
        "runner_timed_out": (
            "Unit test timed out after {timeout:g} seconds and was cancelled."
        ),
    },
    "fr": {
        "debug_prompt_title": "Debogage - Invite LLM ({call_type})",
        "display_busy": (
            "**notebook-ta est déjà en cours d'exécution:** Réessayez lorsque la requête en cours sera terminée."
        ),
        "display_hints_busy_status": (
            "notebook-ta est déjà en cours d'exécution. Réessayez lorsque la requête en cours sera terminée."
        ),
        "display_hints_busy_button": "Requête en cours, patientez...",
        "display_hints_button": "Donnez-moi un indice",
        "display_hints_fetching": "Recherche des indices...",
        "display_execution_failure_heading": "Échec de l'exécution du code",
        "display_execution_failure_detail": (
            "Les tests et l'analyse LLM n'ont pas été lancés. "
            "Corrigez l'erreur et exécutez à nouveau la cellule."
        ),
        "display_hints_tooltip": "Demander des indices.",
        "display_llm_answer_prefix": "🤖",
        "display_llm_unavailable_heading": "LLM indisponible",
        "display_success": "**✅ Tous les tests ont réussi !** Génération de l'analyse...",
        "display_test_results_heading": "Résultats des tests",
        "display_unavailable": (
            "**Exercice `{exercise_id}` introuvable.**\n\n"
            "Avez-vous appelé `notebook_ta.load()` ?"
        ),
        "hardware_detected": (
            "**💻 notebook-ta matériel détecté** - sélection automatique du modèle:\n\n"
            "- RAM : {ram_gb:.1f} Go{gpu_text}\n"
            "- **Modèle sélectionné :** `{model_name}` - {model_description}"
        ),
        "hardware_gpu_text": ", GPU : {gpu_name} ({vram_gb:.1f} Go VRAM)",
        "hardware_no_model": (
            "**💻 notebook-ta détection automatique du matériel :** aucun modèle adapté à votre "
            "matériel n'a été trouvé.\n\n"
            "- RAM : {ram_gb:.1f} Go{gpu_text}\n\n"
            "L'assistant LLM ne sera pas disponible."
        ),
        "initialization_title": "initialisation de notebook-ta",
        "initialization_gpu": ", GPU : {gpu_name} ({vram_gb:.1f} Go VRAM)",
        "initialization_hardware": (
            "💻 Matériel détecté : {ram_gb:.1f} Go de RAM{gpu_text}. "
            "Modèle sélectionné : <code>{model_name}</code> — {model_description}"
        ),
        "initialization_no_model": (
            "⚠️ Matériel détecté : {ram_gb:.1f} Go de RAM{gpu_text}. "
            "Aucun modèle adapté n'a été trouvé."
        ),
        "initialization_loaded": (
            "✅ notebook-ta chargé — fournisseur : <code>{provider}</code>, "
            "modèle : <code>{model}</code>, {exercise_count} exercice(s) enregistré(s)."
        ),
        "load_success": (
            "**✅ notebook-ta chargé:**  Fournisseur : `{provider}` - Modèle : `{model}`  \n"
            "{exercise_count} exercice(s) enregistre(s)."
        ),
        "ollama_setup_checking_server": "Vérification du serveur Ollama local…",
        "ollama_setup_starting_server": "Ollama n'est pas lancé — démarrage du serveur…",
        "ollama_setup_server_failed": (
            "❌ Le serveur Ollama local n'a pas pu être démarré. "
            "Les retours du LLM resteront indisponibles."
        ),
        "ollama_setup_checking_model": "Vérification du modèle Ollama sélectionné…",
        "ollama_setup_pulling_model": "Téléchargement du modèle Ollama sélectionné…",
        "ollama_setup_model_failed": (
            "❌ Le modèle Ollama sélectionné n'a pas pu être téléchargé. "
            "Les retours du LLM resteront indisponibles."
        ),
        "ollama_setup_ready": "✅ Le serveur Ollama local et le modèle sont prêts.",
        "runner_inline_function_missing": (
            "Fonction {function_name!r} introuvable dans le test unitaire de l'exercice "
            "{test_name!r}."
        ),
        "runner_inline_multiple_callables": (
            "Plusieurs objets appelables dans le code de test pour l'exercice {test_name!r}; "
            "indiquez 'function' pour lever l'ambiguite. Trouvés : {callables}"
        ),
        "runner_inline_no_callable": (
            "Aucun objet appelable trouvé dans le code de test pour l'exercice {test_name!r}."
        ),
        "runner_missing_student_name": (
            "Le nom {name!r} n'est pas défini."),
        "runner_output_label": "Sortie",
        "runner_student_globals_not_configured": (
            "Le test demande 'student_globals', mais sa configuration ne définit pas "
            "'student_symbols' et n'active pas 'export_student_globals'."
        ),
        "runner_prepare_timeout_failed": (
            "Impossible de preparer le test unitaire pour appliquer le timeout : {error}"
        ),
        "runner_process_no_result": (
            "L'exécution des tests unitaires s'est terminée sans renvoyer de résultat."
        ),
        "runner_timed_out": (
            "L'exécution du test unitaire a dépassé {timeout:g} secondes et a été annulée."
        ),
    },
}

_current_language = DEFAULT_LANGUAGE


def supported_languages() -> tuple[str, ...]:
    """Return the language codes supported by the built-in translation catalog."""
    return tuple(sorted(_TRANSLATIONS))


def resolve_language(language: str) -> str:
    """Return a supported language code, warning and falling back to English if needed."""
    normalized = language.strip().lower().replace("_", "-")
    candidates = [normalized]
    if "-" in normalized:
        candidates.append(normalized.split("-", 1)[0])

    for candidate in candidates:
        if candidate in _TRANSLATIONS:
            return candidate

    _log.warning(
        "Unsupported language %r requested; falling back to %r. Supported languages: %s",
        language,
        DEFAULT_LANGUAGE,
        ", ".join(supported_languages()),
    )
    return DEFAULT_LANGUAGE


def set_language(language: str) -> str:
    """Set the process-wide notebook display language and return the resolved code."""
    global _current_language
    _current_language = resolve_language(language)
    return _current_language


def get_language() -> str:
    """Return the current process-wide notebook display language."""
    return _current_language


def translate(
    key: str,
    values: Mapping[str, Any] | None = None,
    *,
    language: str | None = None,
) -> str:
    """Return the translated message for *key* formatted with optional values."""
    language_code = resolve_language(language) if language is not None else _current_language
    template = _TRANSLATIONS.get(language_code, {}).get(key)
    if template is None:
        template = _TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)
    return template.format(**(values or {}))
