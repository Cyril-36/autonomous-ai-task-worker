import asyncio

import pytest

from worker.contracts import Principal
from worker.runtime.queue import DurableQueue
from worker.store import Store


@pytest.mark.asyncio
async def test_queue_runs_one_job_at_a_time_and_recovers_running(tmp_path):
    store = Store(tmp_path / "worker.db")
    principal = Principal(user_id="ravi", email="ravi@example.com",
                          display_name="Ravi", role="operator")
    for run_id in ("r1", "r2"):
        store.create_run(run_id, "Register invoice", principal, "fake")
    store.update_run("r1", status="running")
    active = 0
    max_active = 0
    seen = []

    async def run(run_id, answer=None):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        seen.append(run_id)
        await asyncio.sleep(0.01)
        store.update_run(run_id, status="blocked")
        active -= 1

    queue = DurableQueue(store, run)
    await queue.start()
    await queue.join()
    await queue.stop()
    assert max_active == 1
    assert set(seen) == {"r1", "r2"}
    assert any(event.type == "run_status" and event.data["status"] == "interrupted"
               for event in store.events("r1"))
