"""CLI command for launching the prompt benchmarking GUI."""

from __future__ import annotations

import click


@click.command("bench")
@click.argument("project_file", required=False, type=click.Path(dir_okay=False))
def bench(project_file: str | None) -> None:
    """Launch the benchmarking GUI, optionally offering PROJECT_FILE on its welcome screen."""
    try:
        from notebook_ta.bench.app import main
    except ImportError as exc:
        raise click.ClickException(
            "The benchmarking UI requires the 'bench' extra: pip install 'notebook-ta[bench]'"
        ) from exc
    main(project_file)
