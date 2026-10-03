"""Reconcile all write-ahead records before a resumed model step."""

from __future__ import annotations

from worker.policy.pending import reconcile


async def reconcile_all(store, run_id: str, probes):
    results = []
    for pending in store.pending_for_run(run_id):
        if pending.state != "dispatching":
            continue
        decision = await reconcile(pending, probes)
        store.save_pending(decision.pending)
        store.append_event(run_id, "pending", {"mutation_id": pending.mutation_id,
                                               "state": decision.pending.state,
                                               "reason": decision.pending.reason})
        results.append(decision)
    return results
