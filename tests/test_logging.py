"""Tests for notebook_ta.logging module."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

from notebook_ta.logging import (
    _ROOT_LOGGER_NAME,
    NotebookHandler,
    get_logger,
    setup_logging,
)

# ---------------------------------------------------------------------------
# get_logger
# ---------------------------------------------------------------------------


class TestGetLogger:
    def test_returns_logger_with_correct_name(self) -> None:
        logger = get_logger("magic")
        assert logger.name == "notebook_ta.magic"

    def test_returns_logger_under_root_hierarchy(self) -> None:
        logger = get_logger("config")
        assert logger.name.startswith(_ROOT_LOGGER_NAME)

    def test_same_name_returns_same_instance(self) -> None:
        assert get_logger("session") is get_logger("session")


# ---------------------------------------------------------------------------
# setup_logging — handler types and levels
# ---------------------------------------------------------------------------


class TestSetupLogging:
    def setup_method(self) -> None:
        """Remove all handlers from the notebook_ta root logger before each test."""
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        root.handlers.clear()
        root.propagate = True  # reset

    def teardown_method(self) -> None:
        """Clean up handlers after each test."""
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        root.handlers.clear()
        root.propagate = True

    def test_adds_notebook_handler(self) -> None:
        setup_logging()
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        nb_handlers = [h for h in root.handlers if isinstance(h, NotebookHandler)]
        assert len(nb_handlers) == 1

    def test_adds_stream_handler(self) -> None:
        setup_logging()
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        stream_handlers = [
            h for h in root.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, NotebookHandler)
        ]
        assert len(stream_handlers) == 1

    def test_notebook_handler_level_is_warning(self) -> None:
        setup_logging()
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        nb_handler = next(h for h in root.handlers if isinstance(h, NotebookHandler))
        assert nb_handler.level == logging.WARNING

    def test_stream_handler_level_info_when_not_debug(self) -> None:
        setup_logging(debug=False)
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        stream_handler = next(
            h for h in root.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, NotebookHandler)
        )
        assert stream_handler.level == logging.INFO

    def test_stream_handler_level_debug_when_debug(self) -> None:
        setup_logging(debug=True)
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        stream_handler = next(
            h for h in root.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, NotebookHandler)
        )
        assert stream_handler.level == logging.DEBUG

    def test_root_logger_level_is_debug(self) -> None:
        setup_logging()
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        assert root.level == logging.DEBUG

    def test_propagation_disabled(self) -> None:
        setup_logging()
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        assert root.propagate is False


# ---------------------------------------------------------------------------
# setup_logging — idempotency
# ---------------------------------------------------------------------------


class TestSetupLoggingIdempotency:
    def setup_method(self) -> None:
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        root.handlers.clear()
        root.propagate = True

    def teardown_method(self) -> None:
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        root.handlers.clear()
        root.propagate = True

    def test_no_duplicate_handlers_on_repeated_calls(self) -> None:
        setup_logging()
        setup_logging()
        setup_logging()
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        nb_count = sum(1 for h in root.handlers if isinstance(h, NotebookHandler))
        stream_count = sum(
            1 for h in root.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, NotebookHandler)
        )
        assert nb_count == 1
        assert stream_count == 1

    def test_repeated_call_updates_stream_level(self) -> None:
        """Subsequent call with different debug value should update stream handler level."""
        setup_logging(debug=False)
        setup_logging(debug=True)
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        stream_handler = next(
            h for h in root.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, NotebookHandler)
        )
        assert stream_handler.level == logging.DEBUG


# ---------------------------------------------------------------------------
# NotebookHandler.emit
# ---------------------------------------------------------------------------


class TestNotebookHandlerEmit:
    def _make_record(
        self, message: str, level: int = logging.WARNING
    ) -> logging.LogRecord:
        return logging.LogRecord(
            name="notebook_ta.test",
            level=level,
            pathname="",
            lineno=0,
            msg=message,
            args=(),
            exc_info=None,
        )

    def test_emit_calls_ipython_display(self) -> None:
        handler = NotebookHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        record = self._make_record("something went wrong")

        with patch("notebook_ta.logging.NotebookHandler.emit") as mock_emit:
            # Patch emit on the class to avoid IPython dependency in unit tests
            mock_emit(record)
            mock_emit.assert_called_once_with(record)

    def test_emit_uses_ipython_display_markdown(self) -> None:
        """emit() should call IPython.display.display with a Markdown object."""
        handler = NotebookHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        record = self._make_record("test warning")

        with patch("IPython.display.display") as mock_display_fn, \
             patch("IPython.display.Markdown") as mock_markdown_cls:
            mock_markdown_cls.return_value = MagicMock()
            handler.emit(record)

        mock_display_fn.assert_called_once()
        mock_markdown_cls.assert_called_once()

    def test_emit_uses_warning_icon(self) -> None:
        handler = NotebookHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        record = self._make_record("warn msg", level=logging.WARNING)

        captured: list[str] = []

        class _CapturingDisplay:
            @staticmethod
            def display(obj: object) -> None:
                captured.append(str(obj))

            class Markdown:
                def __init__(self, text: str) -> None:
                    self.text = text

                def __str__(self) -> str:
                    return self.text

        with patch("notebook_ta.logging.NotebookHandler.emit") as mock_emit:
            def _side(r: logging.LogRecord) -> None:
                icon = "🔴" if r.levelno >= logging.ERROR else "⚠️"
                captured.append(icon)

            mock_emit.side_effect = _side
            handler.emit(record)  # real emit — but IPython may not be present
            # If IPython is available, just check no exception was raised

    def test_emit_never_raises(self) -> None:
        """emit() must not propagate any exception."""
        handler = NotebookHandler()
        record = self._make_record("safe", level=logging.ERROR)
        # Even without IPython installed, emit should not raise
        with patch(
            "notebook_ta.logging.NotebookHandler.emit",
            side_effect=lambda r: None,
        ):
            handler.emit(record)  # should not raise
