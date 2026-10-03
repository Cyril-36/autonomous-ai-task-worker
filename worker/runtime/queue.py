"""Single durable runner backed by the stored run statuses."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from worker.contracts import RunStatus


class DurableQueue:
    def __init__(self, store, runner: Callable[[str, str | None], Awaitable[None]]):
        self.store = store
        self.runner = runner
        self.queue: asyncio.Queue[tuple[str, str | None] | None] = asyncio.Queue()
        self.task: asyncio.Task | None = None
        self.queued: set[str] = set()

    async def start(self) -> None:
        if self.task and not self.task.done():
            return
        self.task = asyncio.create_task(self._work())
        for run in reversed(self.store.list_runs()):
            if run.status in {RunStatus.queued, RunStatus.running, RunStatus.interrupted}:
                if run.status == RunStatus.running:
                    self.store.update_run(run.run_id, status="interrupted")
                    self.store.append_event(run.run_id, "run_status", {
                        "status": "interrupted", "reason": "Worker restarted; reconciling saved work.",
                    })
                self.enqueue(run.run_id)

    def enqueue(self, run_id: str, answer: str | None = None) -> None:
        if run_id in self.queued:
            return
        self.queued.add(run_id)
        self.queue.put_nowait((run_id, answer))

    async def join(self) -> None:
        await self.queue.join()

    async def stop(self) -> None:
        if self.task:
            await self.queue.put(None)
            await self.task
            self.task = None

    async def _work(self) -> None:
        while True:
            item = await self.queue.get()
            if item is None:
                self.queue.task_done()
                break
            run_id, answer = item
            try:
                await self.runner(run_id, answer)
            except Exception as exc:  # noqa: BLE001 - isolate one failed run from the queue
                self.store.update_run(run_id, status="failed", phase="done")
                self.store.append_event(run_id, "error", {
                    "code": "worker_error", "message": type(exc).__name__,
                })
                self.store.append_event(run_id, "run_status", {
                    "status": "failed", "reason": "The worker stopped because of an internal error.",
                })
            finally:
                self.queued.discard(run_id)
                self.queue.task_done()
