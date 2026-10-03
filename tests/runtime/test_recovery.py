import pytest

from tests.policy.test_pending import FakeProbes, pending
from worker.runtime.recovery import reconcile_all
from worker.runtime.state import RuntimeState, load_state, save_state
from worker.store import Store


def test_runtime_state_persists_across_new_process(tmp_path):
    path = tmp_path / "worker.db"
    state = RuntimeState("r1", ["Register latest"], {"http://127.0.0.1:8101"})
    state.phase = "execute"
    state.steps = 17
    state.observations_text = ["page one"]
    save_state(path, state)
    restored = load_state(path, "r1")
    assert restored.phase == "execute"
    assert restored.steps == 17
    assert restored.observations_text == ["page one"]


@pytest.mark.asyncio
async def test_restart_reconciles_dispatching_before_resuming(tmp_path):
    store = Store(tmp_path / "worker.db")
    store.save_pending(pending())
    decisions = await reconcile_all(store, "r1", FakeProbes(
        "committed", after={"amount": "48250.00", "due_date": "2026-11-01"},
        current={"amount": "48250.00", "due_date": "2026-11-01"}))
    assert decisions[0].pending.state == "committed"
    assert store.pending_for_run("r1")[0].state == "committed"
