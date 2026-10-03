"""RunService implementation with an explicit frontend replay driver."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException

from worker.config import load_pricing
from worker.contracts import (
    TERMINAL_STATUSES,
    Approval,
    ApprovalStatus,
    Principal,
    RunStatus,
)
from worker.store import Store, utc_now


class RunService:
    def __init__(self, store: Store, *, model: str = "replay", engine: str = "replay"):
        self.store = store
        self.model = model
        self.engine = engine

    def _visible(self, run_id: str, principal: Principal):
        run = self.store.get_run(run_id)
        if not run:
            raise HTTPException(404, detail=("not_found", "Run not found"))
        if principal.role != "admin" and run.principal.user_id != principal.user_id:
            raise HTTPException(403, detail=("forbidden", "This run belongs to another user"))
        return run

    def list(self, principal: Principal):
        runs = self.store.list_runs()
        return runs if principal.role == "admin" else [
            run for run in runs if run.principal.user_id == principal.user_id
        ]

    def submit(self, principal: Principal, request: str):
        if not 1 <= len(request.strip()) <= 2000:
            raise HTTPException(422, detail=("invalid_request", "Request must be 1–2000 characters"))
        run_id = uuid4().hex
        self.store.create_run(run_id, request.strip(), principal, self.model)
        self.store.append_event(run_id, "run_status", {"status": "queued", "reason": "replay_demo"})
        if self.engine == "replay":
            self._replay(run_id, request.strip())
        return self.store.get_run(run_id)

    def _replay(self, run_id: str, request: str) -> None:
        self.store.update_run(run_id, status="running", phase="discover")
        self.store.append_event(run_id, "run_status", {"status": "running", "reason": "replay_demo"})
        self.store.append_event(run_id, "phase", {"phase": "discover"})
        plan = [{"text": "Inspect source", "status": "done"},
                {"text": "Check policy", "status": "doing"},
                {"text": "Verify outcome", "status": "todo"}]
        self.store.append_event(run_id, "plan", {"steps": plan, "revision": 1,
                                                  "reason": "Frontend replay; no business write"})
        self.store.append_event(run_id, "step", {
            "step": 1, "tool": "browser_snapshot", "args": {}, "ok": True,
            "summary": "Replay observation of the sandbox workspace", "duration_ms": 12,
        })
        self.store.update_run(run_id, steps=1)
        lowered = request.casefold()
        if "which larkspur" in lowered or "ambiguous" in lowered:
            question_id = uuid4().hex
            question = "Which supplier do you mean: Larkspur Supplies or Larkspur Logistics?"
            self.store.save_question(question_id, run_id, question)
            self.store.update_run(run_id, status="awaiting_input")
            self.store.append_event(run_id, "question", {"question_id": question_id, "text": question})
            self.store.append_event(run_id, "run_status", {"status": "awaiting_input"})
        elif "large" in lowered or "approval" in lowered:
            approval = Approval(
                approval_id=uuid4().hex, run_id=run_id, intent_hash="replay-only",
                reason="Amount threshold (replay)", changes=[], target_label="Replay invoice",
                target_version=None, policy_version=1, expires_at=utc_now() + timedelta(minutes=15),
            )
            payload = approval.model_dump(mode="json")
            self.store.save_approval(approval.approval_id, run_id, payload)
            self.store.update_run(run_id, status="awaiting_approval")
            self.store.append_event(run_id, "approval", payload)
            self.store.append_event(run_id, "run_status", {"status": "awaiting_approval"})
        else:
            self._finish_replay(run_id)

    def _finish_replay(self, run_id: str) -> None:
        self.store.update_run(run_id, status="completed", phase="done")
        self.store.append_event(run_id, "phase", {"phase": "done"})
        self.store.append_event(run_id, "run_status", {
            "status": "completed", "reason": "replay_demo_only_no_business_write",
        })

    def budget(self, run_id: str | None = None) -> dict:
        pricing = load_pricing()
        budget = {
            "global_spent_inr": "0.00", "global_reserved_inr": "0.00",
            "global_limit_inr": f"{pricing.global_limit_inr:.2f}", "estimated": True,
        }
        if run_id:
            budget.update({"run_spent_inr": "0.00",
                           "run_limit_inr": f"{pricing.run_limit_inr:.2f}"})
        return budget

    def detail(self, run_id: str, principal: Principal) -> dict:
        run = self._visible(run_id, principal)
        events = self.store.events(run_id)
        plans = [event.data for event in events if event.type == "plan"]
        verifications = [event.data for event in events if event.type == "verification"]
        contracts = [event.data.get("contract") for event in events
                     if event.type == "contract" and event.data.get("contract")]
        return {
            "summary": run, "contract": contracts[-1] if contracts else None,
            "plan": {"steps": plans[-1]["steps"], "revision": plans[-1]["revision"]}
            if plans else {"steps": [], "revision": 0},
            "facts": [event.data for event in events if event.type == "fact"],
            "approvals": self.store.approvals(run_id), "question": self.store.question(run_id),
            "verification": verifications[-1] if verifications else None,
            "pending": [], "budget": self.budget(run_id),
            "last_seq": events[-1].seq if events else 0,
        }

    def events(self, run_id: str, principal: Principal, after: int = 0):
        self._visible(run_id, principal)
        return self.store.events(run_id, after)

    def answer(self, run_id: str, principal: Principal, text: str) -> None:
        run = self._visible(run_id, principal)
        if run.status != RunStatus.awaiting_input:
            raise HTTPException(409, detail=("conflict", "Run is not awaiting input"))
        if not text.strip():
            raise HTTPException(422, detail=("invalid_request", "Answer cannot be empty"))
        question = self.store.question(run_id)
        self.store.answer(question["question_id"], text.strip(), principal.email)
        self.store.append_event(run_id, "answer", {
            "question_id": question["question_id"], "text": text.strip(), "by": principal.email,
        })
        self._finish_replay(run_id)

    def decide(self, run_id: str, approval_id: str, principal: Principal,
               decision: str, note: str | None = None) -> dict:
        run = self._visible(run_id, principal)
        if principal.role != "admin" and run.principal.user_id != principal.user_id:
            raise HTTPException(403, detail=("forbidden", "Approval not permitted"))
        matches = [a for a in self.store.approvals(run_id) if a["approval_id"] == approval_id]
        if not matches:
            raise HTTPException(404, detail=("not_found", "Approval not found"))
        approval = Approval.model_validate(matches[0])
        if approval.status != ApprovalStatus.pending:
            raise HTTPException(409, detail=("conflict", "Approval already decided"))
        if approval.expires_at <= utc_now():
            raise HTTPException(409, detail=("approval_expired", "Approval expired"))
        if decision not in {"approve", "reject"}:
            raise HTTPException(422, detail=("invalid_request", "Invalid decision"))
        updated = approval.model_copy(update={
            "status": ApprovalStatus.approved if decision == "approve" else ApprovalStatus.rejected,
            "decided_by": principal.email, "decided_at": utc_now(),
        })
        payload = updated.model_dump(mode="json")
        self.store.save_approval(approval_id, run_id, payload)
        self.store.append_event(run_id, "approval", payload)
        if decision == "approve":
            self._finish_replay(run_id)
        else:
            self.store.update_run(run_id, status="blocked", phase="done")
            self.store.append_event(run_id, "run_status", {
                "status": "blocked", "reason": "approval_rejected",
            })
        return payload

    def cancel(self, run_id: str, principal: Principal) -> None:
        run = self._visible(run_id, principal)
        if run.status in TERMINAL_STATUSES:
            raise HTTPException(409, detail=("conflict", "Run already ended"))
        self.store.update_run(run_id, status="failed", phase="done")
        self.store.append_event(run_id, "run_status", {
            "status": "failed", "reason": "cancelled_by_user",
        })
