from datetime import UTC, datetime, timedelta

from tests.policy.util import intent
from worker.contracts import ApprovalStatus
from worker.policy.approvals import create_approval, decide_approval, intent_hash, validate_approval


def test_approval_expires_and_is_single_use():
    now = datetime(2026, 10, 3, tzinfo=UTC)
    mutation = intent()
    approval = create_approval(mutation, "Amount threshold", 1, now=now)
    assert approval.intent_hash == intent_hash(mutation)
    assert any(change.field == "amount" and change.new == "48250.00"
               for change in approval.changes)
    approved = decide_approval(approval, "approve", "asha@example.com", now=now)
    assert approved.status == ApprovalStatus.approved
    assert validate_approval(approved, mutation, 1, now=now + timedelta(minutes=14))
    assert not validate_approval(approved, mutation, 1, now=now + timedelta(minutes=16))
    used = approved.model_copy(update={"status": ApprovalStatus.used})
    assert not validate_approval(used, mutation, 1, now=now)


def test_approval_invalidated_by_target_or_policy_change():
    now = datetime(2026, 10, 3, tzinfo=UTC)
    mutation = intent()
    approved = decide_approval(create_approval(mutation, "Update", 1, now=now),
                               "approve", "asha@example.com", now=now)
    assert not validate_approval(approved, mutation.model_copy(update={"target_version": 2}),
                                 1, now=now)
    assert not validate_approval(approved, mutation, 2, now=now)
