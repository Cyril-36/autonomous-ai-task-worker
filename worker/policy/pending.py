"""Reconcile uncertain writes using the server's atomic token void endpoint."""

from __future__ import annotations

from dataclasses import dataclass

from worker.contracts import MutationIntent, PendingMutation


@dataclass(frozen=True)
class ReconcileDecision:
    pending: PendingMutation
    retry_allowed: bool


def begin_pending(
    store, intent: MutationIntent, *, before_values: dict[str, str] | None,
    before_version: int | None, retries: int = 0,
) -> PendingMutation:
    if not intent.form_token or not intent.target_key:
        raise ValueError("Mutation needs a token and target key")
    checked = {key: value for key, value in intent.fields.items()
               if key in {"supplier_id", "invoice_number", "amount", "currency", "due_date",
                          "source_doc_id", "contact_name", "contact_email", "remittance_email"}}
    pending = PendingMutation(
        mutation_id=intent.mutation_id, run_id=intent.run_id, form_token=intent.form_token,
        target_key=intent.target_key, before_values=before_values, before_version=before_version,
        intended_values=checked, state="dispatching", retries=retries,
    )
    store.save_pending(pending)
    return pending


async def reconcile(pending: PendingMutation, probes) -> ReconcileDecision:
    if pending.state != "dispatching" or not pending.form_token:
        return ReconcileDecision(pending, False)
    result = await probes.void_operation(pending.form_token)
    status = result["status"]
    current = (await probes.target_by_key(pending.target_key)
               if hasattr(probes, "target_by_key") else
               await probes.invoice_by_key(pending.target_key))
    if status == "committed":
        after = result.get("after") or {}
        matches_after = all(after.get(key) == value for key, value in pending.intended_values.items())
        matches_current = current is not None and all(
            current.get(key) == value for key, value in pending.intended_values.items()
        )
        if matches_after and matches_current:
            return ReconcileDecision(pending.model_copy(update={"state": "committed"}), False)
        return ReconcileDecision(pending.model_copy(update={
            "state": "conflict", "reason": "Committed values differ from intended values",
        }), False)
    if status in {"voided", "rejected"}:
        unchanged = (
            current is None if pending.before_values is None else
            current is not None and current.get("version") == pending.before_version and
            all(current.get(key) == value for key, value in pending.before_values.items())
        )
        if not unchanged:
            return ReconcileDecision(pending.model_copy(update={
                "state": "conflict", "reason": "Target changed before retry",
            }), False)
        retry = pending.retries < 2
        return ReconcileDecision(pending.model_copy(update={
            "state": status, "reason": "Safe to retry with a fresh form" if retry else "Retry limit reached",
        }), retry)
    return ReconcileDecision(pending.model_copy(update={
        "state": "conflict", "reason": f"Unexpected operation state: {status}",
    }), False)
