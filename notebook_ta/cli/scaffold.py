"""notebook-ta CLI scaffold generator."""

from __future__ import annotations

from pathlib import Path

import click
import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

from notebook_ta.bench.cli import bench
from notebook_ta.config.loader import load_exercises


@click.group()
def cli() -> None:
    """notebook-ta — teaching assistant toolkit for Jupyter notebooks."""


cli.add_command(bench)


@cli.command("create-notebook")
@click.argument("exercises_toml", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--global-config",
    default=None,
    type=click.Path(dir_okay=False),
    help="Path to global config TOML (written into the setup cell).",
)
@click.option(
    "--output",
    default="notebook.ipynb",
    type=click.Path(dir_okay=False),
    show_default=True,
    help="Output .ipynb file path.",
)
def create_notebook(exercises_toml: str, global_config: str | None, output: str) -> None:
    """Generate a Jupyter notebook scaffold from EXERCISES_TOML."""
    exercises = load_exercises(exercises_toml)

    nb = new_notebook()
    cells = []

    # 1. Setup cell
    global_arg = f'"{global_config}"' if global_config else '"global_config.toml"'
    setup_code = (
        "import notebook_ta\n"
        f"notebook_ta.load(\n"
        f"    global_config={global_arg},\n"
        f'    exercises_config="{exercises_toml}",\n'
        f")"
    )
    cells.append(new_code_cell(source=setup_code))

    # 2. One pair of cells per exercise
    for ex in exercises:
        # Markdown cell with exercise statement
        md_source = f"## Exercise `{ex.id}`\n\n{ex.statement}"
        if ex.expected_output:
            md_source += f"\n\n**Expected output:**\n```\n{ex.expected_output}\n```"
        if ex.additional_info:
            md_source += f"\n\n{ex.additional_info}"
        cells.append(new_markdown_cell(source=md_source))

        # Code cell with magic
        code_source = f"%%notebook_ta {ex.id}\n# Write your solution here\n"
        cells.append(new_code_cell(source=code_source))

    nb["cells"] = cells
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        nbformat.write(nb, fh)

    click.echo(f"Notebook written to: {output_path}")


@cli.command("setup")
def setup() -> None:
    """Detect hardware and print model recommendations."""
    try:
        from rich.console import Console
        from rich.table import Table

        from notebook_ta.setup_wizard.detector import detect_hardware

        console = Console()
        profile = detect_hardware()

        console.print("\n[bold]Hardware Detection[/bold]")
        console.print(f"  RAM:  {profile.ram_gb:.1f} GB")
        if profile.gpu_name:
            console.print(f"  GPU:  {profile.gpu_name}")
            console.print(f"  VRAM: {profile.vram_gb:.1f} GB")
        else:
            console.print("  GPU:  Not detected")

        console.print("\n[bold]Model Recommendations[/bold]")
        console.print(
            "Configure your [cyan]global_config.toml[/cyan] with the following "
            "[cyan][[llm.available_models]][/cyan] entries and set "
            "[cyan]model = \"auto\"[/cyan] to let notebook-ta select automatically.\n"
        )

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Model", style="cyan")
        table.add_column("Description")
        table.add_column("Min RAM", justify="right")
        table.add_column("Min VRAM", justify="right")
        table.add_column("Fits?", justify="center")

        _SUGGESTED_MODELS = [
            ("llama3.2:1b", "Llama 3.2 1B — fastest, minimal quality", 4.0, 0.0),
            ("llama3.2:3b", "Llama 3.2 3B — good balance of speed and quality", 8.0, 0.0),
            ("llama3.1:8b", "Llama 3.1 8B — high quality, slower", 16.0, 0.0),
            ("llama3.1:70b", "Llama 3.1 70B — best quality, requires large machine", 48.0, 0.0),
        ]

        for model_name, description, min_ram, min_vram in _SUGGESTED_MODELS:
            fits = profile.ram_gb >= min_ram and profile.vram_gb >= min_vram
            fits_str = "✅" if fits else "❌"
            table.add_row(
                model_name,
                description,
                f"{min_ram:.0f} GB",
                f"{min_vram:.0f} GB",
                fits_str,
            )

        console.print(table)

    except ImportError:
        click.echo("Install 'rich' for a formatted table: pip install rich")
        from notebook_ta.setup_wizard.detector import detect_hardware

        profile = detect_hardware()
        click.echo(f"\nHardware detected:")
        click.echo(f"  RAM: {profile.ram_gb:.1f} GB")
        click.echo(f"  GPU: {profile.gpu_name or 'Not detected'}")
        click.echo(f"  VRAM: {profile.vram_gb:.1f} GB")
