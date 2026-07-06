"""Notebook statement extractor — reads markdown cells to find exercise statements.

Instructors can embed exercise statements directly in their ``.ipynb`` file by
wrapping the content in a ``<div>`` whose ``id`` matches the exercise id::

    <div id="ex1">

    ## Exercise 1 — Add two numbers

    Write a function ``add(a, b)`` that returns ``a + b``.

    </div>

Multiple markdown cells with the same id are concatenated (newline-separated).
Content is stripped of the surrounding ``<div>`` tags before being used as the
statement text.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from IPython.core.interactiveshell import InteractiveShell


class _DivExtractor(HTMLParser):
    """Stateful HTML parser that extracts inner text from ``<div id="...">`` tags."""

    def __init__(self) -> None:
        super().__init__()
        self._results: dict[str, list[str]] = {}
        self._current_id: str | None = None
        self._depth: int = 0  # nesting depth inside the target div
        self._buf: list[str] = []

    # ------------------------------------------------------------------
    # HTMLParser callbacks
    # ------------------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Track opening tags, starting capture when a matching div is found."""
        if tag == "div":
            if self._current_id is None:
                # Not yet inside a target div — check if this one matches
                div_id = dict(attrs).get("id")
                if div_id is not None:
                    self._current_id = div_id
                    self._depth = 1
                    self._buf = []
            else:
                # Already inside a target div — track nesting depth
                self._depth += 1
                self._buf.append(self.get_starttag_text() or f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        """Track closing tags; stop capture when the target div closes."""
        if tag == "div" and self._current_id is not None:
            self._depth -= 1
            if self._depth == 0:
                # Closing the outermost target div — save the captured text
                text = "".join(self._buf).strip()
                self._results.setdefault(self._current_id, []).append(text)
                self._current_id = None
                self._buf = []
            else:
                self._buf.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        """Collect text data while inside a target div."""
        if self._current_id is not None:
            self._buf.append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle self-closing tags inside a target div."""
        if self._current_id is not None:
            self._buf.append(self.get_starttag_text() or f"<{tag}/>")

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def results(self) -> dict[str, list[str]]:
        """Return the raw (per-cell) captured texts keyed by exercise id."""
        return self._results


def extract_statements(notebook_path: Path) -> dict[str, str]:
    """Parse *notebook_path* and return a mapping of exercise id → statement text.

    Searches every markdown cell for ``<div id="...">`` tags and extracts the
    inner content.  Multiple markdown cells that share the same ``id`` are
    concatenated with a newline separator.

    Args:
        notebook_path: Absolute path to an ``.ipynb`` file.

    Returns:
        A dict mapping each discovered exercise id to its full statement string.
        Exercises with no matching div in the notebook are not included.

    Raises:
        ConfigurationError: If the notebook file cannot be read or parsed.
    """
    import nbformat

    from notebook_ta.config.models import ConfigurationError

    try:
        with open(notebook_path, encoding="utf-8") as fh:
            nb = nbformat.read(fh, as_version=4)  # type: ignore[no-untyped-call]
    except FileNotFoundError:
        raise ConfigurationError(f"Notebook file not found: {notebook_path}") from None
    except Exception as exc:
        raise ConfigurationError(
            f"Failed to read notebook {notebook_path}: {exc}"
        ) from exc

    # Accumulate all per-cell fragments across the whole notebook
    accumulated: dict[str, list[str]] = {}

    for cell in nb.cells:
        if cell.cell_type != "markdown":
            continue
        source: str = cell.source if isinstance(cell.source, str) else "".join(cell.source)
        if "<div" not in source:
            continue  # fast skip — no div at all

        parser = _DivExtractor()
        parser.feed(source)
        for exercise_id, fragments in parser.results().items():
            accumulated.setdefault(exercise_id, []).extend(fragments)

    return {eid: "\n".join(parts) for eid, parts in accumulated.items()}


def detect_notebook_path(ip: InteractiveShell | None) -> Path | None:
    """Best-effort attempt to find the current notebook's file path.

    Tries, in order:
    1. ``__vsc_ipynb_file__`` in the IPython user namespace (VS Code Jupyter).
    2. ``ipynbname.path()`` as a fallback.

    Returns ``None`` if the path cannot be determined automatically; in that
    case the caller should ask the user to pass ``notebook_path=`` explicitly.

    Args:
        ip: The active IPython ``InteractiveShell`` instance, or ``None``.

    Returns:
        The resolved ``Path`` to the notebook, or ``None``.
    """
    if ip is not None:
        vsc_path = ip.user_ns.get("__vsc_ipynb_file__")
        if vsc_path:
            return Path(vsc_path)

    try:
        import ipynbname

        return Path(ipynbname.path())
    except Exception:
        return None
