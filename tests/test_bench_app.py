"""Tests for the loopback-only benchmark application bootstrap."""

from __future__ import annotations

from unittest.mock import patch

from notebook_ta.bench import app


def test_main_binds_benchmark_server_to_ipv4_loopback() -> None:
    """The benchmark GUI must never rely on NiceGUI's network-facing host default."""
    with (
        patch.object(app.ui, "page", return_value=lambda function: function),
        patch.object(app.ui, "run") as run,
        patch.object(app, "get_last_project_path", return_value=None),
    ):
        app.main()

    run.assert_called_once_with(
        title="Notebook-TA Benchmarking",
        host="127.0.0.1",
        reload=False,
        show=True,
        port=0,
    )
