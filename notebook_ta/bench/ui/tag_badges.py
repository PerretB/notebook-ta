"""Shared rendering helpers for colored benchmark solution tags."""

from __future__ import annotations

from nicegui import ui

from notebook_ta.bench.models import BenchSettings


def render_tag_badge(settings: BenchSettings, tag: str) -> ui.badge:
    """Render ``tag`` as a badge using its configured project color."""
    color = settings.color_for_tag(tag)
    text_color = _contrasting_text_color(color)
    return ui.badge(tag, color=color, text_color=text_color)


def _contrasting_text_color(background: str) -> str:
    """Choose readable black or white text for a six-digit hex background."""
    red, green, blue = (int(background[index : index + 2], 16) for index in (1, 3, 5))
    luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
    return "black" if luminance > 0.6 else "white"
