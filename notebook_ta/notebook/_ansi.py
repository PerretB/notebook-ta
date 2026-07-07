"""Utilities for rendering terminal ANSI sequences in HTML contexts."""

from __future__ import annotations

import html
import re

_ANSI_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")
_ANSI_COLORS = {
    30: "#000000",
    31: "#aa0000",
    32: "#00aa00",
    33: "#aa5500",
    34: "#0000aa",
    35: "#aa00aa",
    36: "#00aaaa",
    37: "#aaaaaa",
    90: "#555555",
    91: "#ff5555",
    92: "#00c000",
    93: "#d4a000",
    94: "#5555ff",
    95: "#ff55ff",
    96: "#00b8b8",
    97: "#ffffff",
}


def ansi_to_html(value: str) -> str:
    """Convert common ANSI SGR sequences to escaped inline HTML."""
    parts: list[str] = []
    position = 0
    bold = False
    underline = False
    color: str | None = None
    span_open = False

    for match in _ANSI_SGR_RE.finditer(value):
        parts.append(html.escape(value[position : match.start()]))
        if span_open:
            parts.append("</span>")

        codes = [int(code) if code else 0 for code in match.group(1).split(";")]
        for code in codes:
            if code == 0:
                bold = False
                underline = False
                color = None
            elif code == 1:
                bold = True
            elif code == 4:
                underline = True
            elif code == 22:
                bold = False
            elif code == 24:
                underline = False
            elif code == 39:
                color = None
            elif code in _ANSI_COLORS:
                color = _ANSI_COLORS[code]

        styles: list[str] = []
        if color:
            styles.append(f"color: {color}")
        if bold:
            styles.append("font-weight: bold")
        if underline:
            styles.append("text-decoration: underline")
        if styles:
            parts.append(f'<span style="{"; ".join(styles)}">')
            span_open = True
        else:
            span_open = False
        position = match.end()

    parts.append(html.escape(value[position:]))
    if span_open:
        parts.append("</span>")
    return "".join(parts)
