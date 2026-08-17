"""Streaming LLM responses to notebook output."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

from IPython import display as ipydisplay

from notebook_ta.i18n import translate
from notebook_ta.llm.base import LLMStreamChunk
from notebook_ta.notebook.display import (
    format_llm_answer_markdown,
    format_llm_waiting_markdown,
)


async def stream_to_output(
    async_gen: AsyncIterator[str | LLMStreamChunk],
    *,
    postprocessor: Callable[[str, bool], Awaitable[str]] | None = None,
    show_thinking: bool = False,
) -> str:
    """Stream LLM chunks into a Markdown display updated in place.

    1. An animated waiting indicator is displayed immediately with a stable
       display ID.
    2. Incoming chunks are accumulated; on each chunk the display is updated
       in place via the display handle — no duplicate outputs.
    3. Returns the final displayed response once the stream ends.

    Args:
        async_gen: An async generator yielding text or categorized chunks from the LLM.
        postprocessor: Optional asynchronous transformation applied to the accumulated
            answer after every chunk and once more when the answer is complete.
        show_thinking: Whether categorized thinking chunks should be rendered before the answer.

    Returns:
        The final processed response, or the raw concatenated response when no
        postprocessor is configured.
    """
    accumulated: list[str] = []
    thinking: list[str] = []
    stream_completed = False
    rendered_answer = False
    handle = cast(Any, ipydisplay.display)(
        cast(Any, ipydisplay.Markdown)(format_llm_waiting_markdown()),
        display_id=True,
    )

    def _with_thinking(answer: str) -> str:
        """Prefix an answer with accumulated thinking when debug rendering is enabled."""
        if not show_thinking or not thinking:
            return answer
        return (
            f"**{translate('display_llm_thinking_prefix')}:**\n\n"
            f"{''.join(thinking)}\n\n"
            f"**{translate('display_llm_final_answer_prefix')}:**\n\n"
            f"{answer}"
        )

    try:
        async for chunk in async_gen:
            if isinstance(chunk, LLMStreamChunk):
                if chunk.kind == "thinking":
                    thinking.append(chunk.content)
                else:
                    accumulated.append(chunk.content)
            else:
                accumulated.append(chunk)
            full_text = "".join(accumulated)
            displayed_text = (
                await postprocessor(full_text, False)
                if postprocessor is not None
                else full_text
            )
            displayed_text = _with_thinking(displayed_text)
            if handle is not None:
                handle.update(
                    cast(Any, ipydisplay.Markdown)(
                        format_llm_answer_markdown(displayed_text)
                    )
                )
                rendered_answer = True
        stream_completed = True
    finally:
        if handle is not None and not stream_completed and not rendered_answer:
            handle.update(cast(Any, ipydisplay.Markdown)(format_llm_answer_markdown("")))

    answer = "".join(accumulated)
    if postprocessor is not None:
        answer = await postprocessor(answer, True)
        if handle is not None:
            handle.update(
                cast(Any, ipydisplay.Markdown)(
                    format_llm_answer_markdown(_with_thinking(answer))
                )
            )
    elif not accumulated and handle is not None:
        handle.update(
            cast(Any, ipydisplay.Markdown)(
                format_llm_answer_markdown(_with_thinking(""))
            )
        )
    return answer
