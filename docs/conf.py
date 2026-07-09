"""Sphinx configuration for notebook-ta."""

from __future__ import annotations

from importlib.metadata import metadata, version
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

project = "notebook-ta"
author = metadata("notebook-ta").get("Author", "notebook-ta contributors")
copyright = "2026, notebook-ta contributors"
release = version("notebook-ta")
version = release

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
master_doc = "index"

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_title = f"{project} {release}"

autodoc_typehints = "description"
autodoc_member_order = "bysource"

myst_enable_extensions = [
    "colon_fence",
    "deflist",
]
myst_heading_anchors = 3
