"""Streaming LLM responses to notebook output."""

from __future__ import annotations

from typing import AsyncIterator

from IPython import display as ipydisplay


async def stream_to_output(async_gen: AsyncIterator[str]) -> str:
    """Stream LLM chunks into a Markdown display updated in place.

    1. An empty Markdown placeholder is displayed immediately with a stable
       display ID.
    2. Incoming chunks are accumulated; on each chunk the display is updated
       in place via the display handle — no duplicate outputs.
    3. Returns the complete accumulated response once the stream ends.

    Args:
        async_gen: An async generator yielding text chunks from the LLM.

    Returns:
        The full concatenated response string.
    """
    accumulated: list[str] = []
    handle = ipydisplay.display(ipydisplay.Markdown(""), display_id=True)

    async for chunk in async_gen:
        accumulated.append(chunk)
        full_text = "".join(accumulated)
        if handle is not None:
            handle.update(ipydisplay.Markdown(full_text))

    return "".join(accumulated)
