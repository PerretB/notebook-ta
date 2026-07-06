"""Central logging utilities for notebook-ta.

All modules obtain their logger via :func:`get_logger` which namespaces them
under the ``notebook_ta`` hierarchy.  Configuration is done once by
:func:`setup_logging`, called from :func:`notebook_ta.load`.

Two handlers are configured:

* **StreamHandler(sys.stderr)** — writes to the terminal / Jupyter server
  console.  Level is ``DEBUG`` when *debug* mode is on, ``INFO`` otherwise.
* **NotebookHandler** — displays ``WARNING`` and above as formatted Markdown
  directly in the notebook cell output area using ``IPython.display``.
"""

from __future__ import annotations

import logging
import sys

_ROOT_LOGGER_NAME = "notebook_ta"


def get_logger(name: str) -> logging.Logger:
    """Return a logger namespaced under ``notebook_ta``.

    Args:
        name: Sub-name appended to ``notebook_ta.``, e.g. ``"magic"`` yields
              a logger named ``notebook_ta.magic``.

    Returns:
        A :class:`logging.Logger` instance.
    """
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{name}")


class NotebookHandler(logging.Handler):
    """Logging handler that surfaces WARNING+ records as inline notebook output.

    Records are rendered as Markdown via ``IPython.display.display`` so that
    warnings and errors appear directly in the notebook cell output area.
    This handler must never raise — any internal error falls back to
    :meth:`handleError`.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Render *record* as a Markdown warning block in the notebook output.

        Args:
            record: The log record to display.
        """
        try:
            from IPython import display as ipydisplay

            icon = "🔴" if record.levelno >= logging.ERROR else "⚠️"
            msg = self.format(record)
            ipydisplay.display(  # type: ignore[no-untyped-call]
                ipydisplay.Markdown(  # type: ignore[no-untyped-call]
                    f"{icon} **[notebook-ta {record.levelname}]** {msg}"
                )
            )
        except Exception:  # pragma: no cover — safety net
            self.handleError(record)


def setup_logging(debug: bool = False) -> None:
    """Configure the root ``notebook_ta`` logger.

    Idempotent — safe to call multiple times (e.g. when :func:`notebook_ta.load`
    is called more than once in a notebook session).  On repeated calls the
    level of existing handlers is updated rather than new handlers being added.

    Args:
        debug: When ``True``, attach a :class:`logging.StreamHandler` at
               ``DEBUG`` level so that detailed internal events appear on the
               terminal / Jupyter server console.  When ``False`` the
               ``StreamHandler`` is set to ``INFO`` level.  A
               :class:`NotebookHandler` at ``WARNING`` level is always
               present so that warnings and errors appear inline in the
               notebook output.
    """
    root = logging.getLogger(_ROOT_LOGGER_NAME)
    root.setLevel(logging.DEBUG)  # individual handlers decide their threshold

    # Scan existing handlers so we reconfigure rather than duplicate.
    existing_stream: logging.Handler | None = None
    existing_notebook: NotebookHandler | None = None
    for handler in root.handlers:
        if isinstance(handler, NotebookHandler):
            existing_notebook = handler
        elif isinstance(handler, logging.StreamHandler):
            existing_stream = handler

    stream_level = logging.DEBUG if debug else logging.INFO

    if existing_stream is not None:
        existing_stream.setLevel(stream_level)
    else:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setLevel(stream_level)
        stream_handler.setFormatter(
            logging.Formatter("[notebook-ta %(levelname)s] %(name)s: %(message)s")
        )
        root.addHandler(stream_handler)

    if existing_notebook is not None:
        existing_notebook.setLevel(logging.WARNING)
    else:
        nb_handler = NotebookHandler()
        nb_handler.setLevel(logging.WARNING)
        nb_handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(nb_handler)

    # Prevent double-printing via the root Python logger in some Jupyter environments.
    root.propagate = False
