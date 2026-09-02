"""Tests for serial notebook LLM dispatch and cancellation."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from notebook_ta.notebook.dispatcher import LLMDispatcher
from notebook_ta.notebook.display import LLMOutput


def make_output() -> MagicMock:
    """Return a display mock constrained to the LLMOutput interface."""
    return MagicMock(spec=LLMOutput)


async def test_dispatcher_runs_jobs_in_fifo_order() -> None:
    """Only one operation runs and later work starts in submission order."""
    dispatcher = LLMDispatcher()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    order: list[str] = []

    async def first() -> str:
        order.append("first-start")
        first_started.set()
        await release_first.wait()
        order.append("first-end")
        return "first"

    async def second() -> str:
        order.append("second")
        return "second"

    first_result = dispatcher.enqueue(first, make_output())
    second_result = dispatcher.enqueue(second, make_output())
    assert isinstance(first_result, asyncio.Future)
    assert isinstance(second_result, asyncio.Future)

    await first_started.wait()
    assert order == ["first-start"]
    release_first.set()

    assert await first_result == "first"
    assert await second_result == "second"
    assert order == ["first-start", "first-end", "second"]


async def test_cancel_pending_job_never_invokes_operation() -> None:
    """A request cancelled before its turn is finalized without provider work."""
    dispatcher = LLMDispatcher()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_called = False
    pending_output = make_output()

    async def first() -> None:
        first_started.set()
        await release_first.wait()

    async def second() -> None:
        nonlocal second_called
        second_called = True

    first_result = dispatcher.enqueue(first, make_output())
    second_result = dispatcher.enqueue(second, pending_output)
    assert isinstance(first_result, asyncio.Future)
    assert isinstance(second_result, asyncio.Future)
    await first_started.wait()

    assert dispatcher.cancel(2) is True
    assert second_result.cancelled()
    pending_output.show_cancelled.assert_called_once_with()

    release_first.set()
    await first_result
    assert second_called is False


async def test_cancel_active_job_releases_next_job() -> None:
    """Cancelling the active stream preserves queue progress."""
    dispatcher = LLMDispatcher()
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    active_output = make_output()

    async def first() -> None:
        first_started.set()
        await asyncio.Event().wait()

    async def second() -> str:
        second_started.set()
        return "second"

    first_result = dispatcher.enqueue(first, active_output)
    second_result = dispatcher.enqueue(second, make_output())
    assert isinstance(first_result, asyncio.Future)
    assert isinstance(second_result, asyncio.Future)
    await first_started.wait()

    assert dispatcher.cancel(1) is True
    await second_started.wait()
    with pytest.raises(asyncio.CancelledError):
        await first_result
    assert await second_result == "second"
    active_output.show_cancelled.assert_called_once_with()


async def test_cancel_all_drains_pending_and_active_jobs() -> None:
    """Cancel all terminates the stream and every queued request."""
    dispatcher = LLMDispatcher()
    active_started = asyncio.Event()
    outputs = [make_output() for _ in range(3)]

    async def active() -> None:
        active_started.set()
        await asyncio.Event().wait()

    async def pending() -> None:
        raise AssertionError("pending operation should not start")

    results = [
        dispatcher.enqueue(active, outputs[0]),
        dispatcher.enqueue(pending, outputs[1]),
        dispatcher.enqueue(pending, outputs[2]),
    ]
    assert all(isinstance(result, asyncio.Future) for result in results)
    await active_started.wait()

    assert dispatcher.cancel_all() == 3
    for result in results:
        assert isinstance(result, asyncio.Future)
        with pytest.raises(asyncio.CancelledError):
            await result
    for output in outputs:
        output.show_cancelled.assert_called_once_with()
    assert dispatcher.pending_count == 0


async def test_shutdown_is_idempotent_and_rejects_new_work() -> None:
    """Shutdown may be repeated and prevents work from surviving teardown."""
    dispatcher = LLMDispatcher()
    started = asyncio.Event()

    async def operation() -> None:
        started.set()
        await asyncio.Event().wait()

    result = dispatcher.enqueue(operation, make_output())
    assert isinstance(result, asyncio.Future)
    await started.wait()

    await dispatcher.shutdown()
    await dispatcher.shutdown()
    assert result.cancelled()
    assert dispatcher.is_active is False
    with pytest.raises(RuntimeError, match="shut down"):
        dispatcher.enqueue(operation, make_output())
