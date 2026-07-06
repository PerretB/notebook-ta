"""Native OS file/directory picker helpers, used by the Settings tab.

Uses `tkinter.filedialog` in a background thread (via an executor) so the blocking
native dialog doesn't stall NiceGUI's asyncio event loop. Falls back to returning
`None` (silently) if `tkinter` isn't available (e.g. headless Linux servers) -- the
caller should keep the plain text input as a fallback in that case.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from notebook_ta.logging import get_logger

_log = get_logger("bench.native_dialogs")

PickMode = Literal["open_file", "save_file", "directory"]


def _pick_sync(
    mode: PickMode,
    filetypes: list[tuple[str, str]] | None,
    defaultextension: str | None,
    initialfile: str | None,
) -> str | None:
    """Blocking implementation, run off the event loop via `run_in_executor`."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        _log.debug("tkinter is not available; native picker disabled.")
        return None

    root = tk.Tk()
    root.withdraw()
    root.wm_attributes("-topmost", 1)
    try:
        if mode == "open_file":
            path = filedialog.askopenfilename(filetypes=filetypes or [("All files", "*.*")])
        elif mode == "save_file":
            path = filedialog.asksaveasfilename(
                filetypes=filetypes or [("All files", "*.*")],
                defaultextension=defaultextension or "",
                initialfile=initialfile or "",
            )
        else:
            path = filedialog.askdirectory()
    finally:
        root.destroy()
    return path or None


async def pick_path(
    mode: PickMode,
    *,
    filetypes: list[tuple[str, str]] | None = None,
    defaultextension: str | None = None,
    initialfile: str | None = None,
) -> str | None:
    """Open a native OS picker dialog; return the chosen path, or None if cancelled/unavailable."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _pick_sync, mode, filetypes, defaultextension, initialfile
    )
