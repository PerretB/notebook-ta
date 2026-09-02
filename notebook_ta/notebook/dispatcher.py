"""Serial, cancellable dispatch of notebook LLM operations."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, TypeVar

from notebook_ta.logging import get_logger
from notebook_ta.notebook.display import LLMOutput

_log = get_logger("notebook.dispatcher")
_T = TypeVar("_T")


@dataclass
class _QueuedJob:
    """One pending or active dispatcher operation."""

    request_id: int
    operation: Callable[[], Coroutine[Any, Any, Any]]
    output: LLMOutput
    completion: asyncio.Future[Any]
    cancel_requested: bool = False


class LLMDispatcher:
    """Run queued LLM operations serially and expose explicit cancellation."""

    def __init__(self) -> None:
        """Create an empty dispatcher that accepts jobs until shutdown."""
        self._pending: deque[_QueuedJob] = deque()
        self._active: _QueuedJob | None = None
        self._active_task: asyncio.Task[Any] | None = None
        self._worker_task: asyncio.Task[None] | None = None
        self._next_request_id = 1
        self._closed = False

    def enqueue(
        self,
        operation: Callable[[], Coroutine[Any, Any, _T]],
        output: LLMOutput,
    ) -> asyncio.Future[_T] | _T:
        """Append an operation and return its asynchronous or immediate result."""
        if self._closed:
            output.show_cancelled()
            raise RuntimeError("The LLM dispatcher has been shut down.")

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
            output.bind_cancellation(lambda: False, lambda: 0)
            return loop.run_until_complete(self._run_immediately(operation, output))

        request_id = self._next_request_id
        self._next_request_id += 1
        completion: asyncio.Future[_T] = loop.create_future()
        completion.add_done_callback(self._consume_completion_exception)
        job = _QueuedJob(
            request_id=request_id,
            operation=operation,
            output=output,
            completion=completion,
        )
        output.bind_cancellation(
            lambda: self.cancel(request_id),
            self.cancel_all,
        )
        completion.add_done_callback(
            lambda future: self.cancel(request_id) if future.cancelled() else None
        )
        self._pending.append(job)
        self._ensure_worker(loop)
        return completion

    def cancel(self, request_id: int) -> bool:
        """Cancel one active or pending request, returning whether it was found."""
        if self._active is not None and self._active.request_id == request_id:
            if self._active_task is not None and not self._active_task.done():
                self._active.cancel_requested = True
                self._render_cancelled(self._active)
                self._active_task.cancel()
            return True

        for job in self._pending:
            if job.request_id != request_id:
                continue
            self._pending.remove(job)
            self._render_cancelled(job)
            if not job.completion.done():
                job.completion.cancel()
            return True
        return False

    def cancel_all(self) -> int:
        """Cancel the active request and drain all pending requests."""
        cancelled = 0
        pending = list(self._pending)
        self._pending.clear()
        for job in pending:
            self._render_cancelled(job)
            if not job.completion.done():
                job.completion.cancel()
            cancelled += 1

        if self._active is not None:
            if self._active_task is not None and not self._active_task.done():
                self._active.cancel_requested = True
                self._render_cancelled(self._active)
                self._active_task.cancel()
                cancelled += 1
        return cancelled

    async def shutdown(self) -> None:
        """Reject new work, cancel outstanding requests, and await worker exit."""
        self._closed = True
        self.cancel_all()
        worker = self._worker_task
        if worker is not None and worker is not asyncio.current_task():
            try:
                await worker
            except asyncio.CancelledError:
                pass

    def shutdown_now(self) -> None:
        """Best-effort synchronous shutdown for interpreter and kernel teardown."""
        self._closed = True
        self.cancel_all()

    @property
    def pending_count(self) -> int:
        """Return the number of requests waiting behind the active request."""
        return len(self._pending)

    @property
    def is_active(self) -> bool:
        """Return whether an LLM operation is currently running."""
        return self._active is not None

    async def _run_immediately(
        self,
        operation: Callable[[], Coroutine[Any, Any, _T]],
        output: LLMOutput,
    ) -> _T:
        """Run one operation in synchronous IPython and test environments."""
        try:
            result = await operation()
        except asyncio.CancelledError:
            output.show_cancelled()
            raise
        try:
            output.mark_completed()
        except Exception as exc:
            _log.debug("Could not finalize immediate LLM output: %s", exc)
        return result

    def _ensure_worker(self, loop: asyncio.AbstractEventLoop) -> None:
        """Start the queue worker if no live worker currently exists."""
        if self._worker_task is not None and not self._worker_task.done():
            return
        self._worker_task = loop.create_task(self._run_worker())
        self._worker_task.add_done_callback(self._worker_finished)

    async def _run_worker(self) -> None:
        """Process queued jobs one at a time until the queue becomes empty."""
        while self._pending:
            job = self._pending.popleft()
            self._active = job
            self._active_task = asyncio.create_task(job.operation())
            try:
                result = await self._active_task
            except asyncio.CancelledError:
                if not job.cancel_requested:
                    self._render_cancelled(job)
                if not job.completion.done():
                    job.completion.cancel()
            except Exception as exc:
                _log.warning("Unhandled queued LLM operation failure: %s", exc)
                try:
                    job.output.show_failed(str(exc))
                except Exception as display_exc:
                    _log.debug("Could not render failed LLM output: %s", display_exc)
                if not job.completion.done():
                    job.completion.set_exception(exc)
            else:
                try:
                    job.output.mark_completed()
                except Exception as exc:
                    _log.debug("Could not finalize queued LLM output: %s", exc)
                if not job.completion.done():
                    job.completion.set_result(result)
            finally:
                self._active_task = None
                self._active = None

    def _worker_finished(self, task: asyncio.Task[None]) -> None:
        """Consume worker failures and clear the retained worker reference."""
        if self._worker_task is task:
            self._worker_task = None
        if task.cancelled():
            return
        try:
            task.exception()
        except Exception as exc:
            _log.warning("LLM dispatcher worker failed: %s", exc)

    @staticmethod
    def _render_cancelled(job: _QueuedJob) -> None:
        """Best-effort cancellation rendering that cannot stall queue cleanup."""
        try:
            job.output.show_cancelled()
        except Exception as exc:
            _log.debug("Could not render cancelled LLM output: %s", exc)

    @staticmethod
    def _consume_completion_exception(future: asyncio.Future[Any]) -> None:
        """Prevent ignored automatic-analysis futures from logging exceptions."""
        if future.cancelled():
            return
        try:
            future.exception()
        except Exception:
            pass
