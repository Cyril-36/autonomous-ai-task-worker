from tests.policy.util import intent
from worker.policy.pending import begin_pending
from worker.store import Store


def test_pending_is_persisted_before_network_dispatch(tmp_path):
    store = Store(tmp_path / "worker.db")
    pending = begin_pending(store, intent(), before_values=None, before_version=None)
    assert pending.state == "dispatching"
    assert store.pending_for_run("r1") == [pending]
