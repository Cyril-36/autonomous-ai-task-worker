import pytest

from worker.contracts import PendingMutation
from worker.policy.pending import reconcile


class FakeProbes:
    def __init__(self, status, after=None, current=None):
        self.status = status
        self.after = after
        self.current = current
        self.void_calls = 0

    async def void_operation(self, token):
        self.void_calls += 1
        return {"status": self.status, "after": self.after}

    async def invoice_by_key(self, target_key):
        return self.current


def pending(**changes):
    base = PendingMutation(
        mutation_id="m1", run_id="r1", form_token="t1",
        target_key={"supplier_id": "larkspur-supplies", "invoice_number": "LS-1042"},
        before_values=None, before_version=None,
        intended_values={"amount": "48250.00", "due_date": "2026-11-01"},
        state="dispatching",
    )
    return base.model_copy(update=changes)


@pytest.mark.asyncio
async def test_committed_matching_operation_never_retries():
    probe = FakeProbes("committed", after={"amount": "48250.00", "due_date": "2026-11-01"},
                       current={"amount": "48250.00", "due_date": "2026-11-01"})
    result = await reconcile(pending(), probe)
    assert result.pending.state == "committed"
    assert not result.retry_allowed
    assert probe.void_calls == 1


@pytest.mark.asyncio
async def test_committed_wrong_value_is_conflict():
    probe = FakeProbes("committed", after={"amount": "48250.00", "due_date": "2026-11-02"},
                       current={"amount": "48250.00", "due_date": "2026-11-02"})
    result = await reconcile(pending(), probe)
    assert result.pending.state == "conflict"
    assert not result.retry_allowed


@pytest.mark.asyncio
async def test_voided_allows_bounded_retry_only_when_unchanged():
    probe = FakeProbes("voided", current=None)
    assert (await reconcile(pending(), probe)).retry_allowed
    assert not (await reconcile(pending(retries=2), probe)).retry_allowed
    update = pending(before_values={"amount": "100.00"}, before_version=1)
    changed = FakeProbes("voided", current={"amount": "200.00", "version": 2})
    result = await reconcile(update, changed)
    assert result.pending.state == "conflict"
    assert not result.retry_allowed


@pytest.mark.asyncio
async def test_server_rejected_write_can_retry_if_target_unchanged():
    result = await reconcile(pending(), FakeProbes("rejected", current=None))
    assert result.pending.state == "rejected"
    assert result.retry_allowed


@pytest.mark.asyncio
async def test_supplier_update_reconciles_by_supplier_key():
    class SupplierProbes(FakeProbes):
        async def target_by_key(self, target_key):
            return {"id": target_key["supplier_id"], "contact_name": "Nina Sen",
                    "version": 2}

    update = pending(target_key={"supplier_id": "larkspur-supplies"},
                     before_values={"contact_name": "Old"}, before_version=1,
                     intended_values={"contact_name": "Nina Sen"})
    result = await reconcile(update, SupplierProbes("committed",
        after={"contact_name": "Nina Sen"}))
    assert result.pending.state == "committed"
