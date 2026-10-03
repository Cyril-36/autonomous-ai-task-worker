"""Approval binds one exact mutation, target version and policy version."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from worker.contracts import Approval, ApprovalStatus, MutationIntent, ValueChange


def intent_hash(intent: MutationIntent) -> str:
    return hashlib.sha256(intent.model_dump_json(
        exclude={"secret_fields", "mutation_id"}).encode()).hexdigest()


def create_approval(
    intent: MutationIntent, reason: str, policy_version: int, *,
    now: datetime | None = None, before_values: dict[str, str] | None = None,
) -> Approval:
    created = now or datetime.now(UTC)
    before_values = before_values or {}
    changes = [ValueChange(field=key, old=before_values.get(key), new=value)
               for key, value in intent.fields.items()
               if key not in {"form_token", "version"} and before_values.get(key) != value]
    return Approval(
        approval_id=uuid4().hex, run_id=intent.run_id, intent_hash=intent_hash(intent),
        reason=reason, changes=changes,
        target_label=", ".join(intent.target_key.values()) if intent.target_key else intent.action_url,
        target_version=intent.target_version, policy_version=policy_version,
        expires_at=created + timedelta(minutes=15),
    )


def decide_approval(
    approval: Approval, decision: str, by: str, *, now: datetime | None = None,
) -> Approval:
    when = now or datetime.now(UTC)
    if approval.status != ApprovalStatus.pending or approval.expires_at <= when:
        raise ValueError("Approval is no longer pending")
    if decision not in {"approve", "reject"}:
        raise ValueError("Invalid approval decision")
    return approval.model_copy(update={
        "status": ApprovalStatus.approved if decision == "approve" else ApprovalStatus.rejected,
        "decided_by": by, "decided_at": when,
    })


def validate_approval(
    approval: Approval, intent: MutationIntent, policy_version: int, *,
    now: datetime | None = None,
) -> bool:
    when = now or datetime.now(UTC)
    return (
        approval.status == ApprovalStatus.approved
        and approval.expires_at > when
        and approval.run_id == intent.run_id
        and approval.intent_hash == intent_hash(intent)
        and approval.target_version == intent.target_version
        and approval.policy_version == policy_version
    )
