"""Mutable, run-scoped execution state kept outside the shared contracts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from worker.contracts import Approval, Fact, GoalContract, Observation, PendingMutation


@dataclass
class RuntimeState:
    run_id: str
    user_messages: list[str]
    allowed_origins: set[str]
    phase: str = "setup"
    contract: GoalContract | None = None
    observations: dict[str, Observation] = field(default_factory=dict)
    facts: dict[str, Fact] = field(default_factory=dict)
    source_values: dict[str, dict[str, str]] = field(default_factory=dict)
    policy: dict = field(default_factory=dict)
    approvals: list[Approval] = field(default_factory=list)
    pending: list[PendingMutation] = field(default_factory=list)
    plan: list[dict] = field(default_factory=list)
    observations_text: list[str] = field(default_factory=list)
    feedback: list[str] = field(default_factory=list)
    steps: int = 0
    wrote_business_data: bool = False
    export_path: str | None = None
    verify_rounds: int = 0
    last_verification: str | None = None


def save_state(path: Path | str, state: RuntimeState) -> None:
    payload = {
        "run_id": state.run_id, "user_messages": state.user_messages,
        "allowed_origins": sorted(state.allowed_origins), "phase": state.phase,
        "contract": state.contract.model_dump(mode="json") if state.contract else None,
        "observations": {key: value.model_dump(mode="json")
                         for key, value in state.observations.items()},
        "facts": {key: value.model_dump(mode="json") for key, value in state.facts.items()},
        "source_values": state.source_values, "policy": state.policy,
        "approvals": [value.model_dump(mode="json") for value in state.approvals],
        "pending": [value.model_dump(mode="json") for value in state.pending],
        "plan": state.plan, "observations_text": state.observations_text,
        "feedback": state.feedback, "steps": state.steps,
        "wrote_business_data": state.wrote_business_data,
        "export_path": state.export_path, "verify_rounds": state.verify_rounds,
        "last_verification": state.last_verification,
    }
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS runtime_states ("
                   "run_id TEXT PRIMARY KEY, data_json TEXT NOT NULL)")
        db.execute("INSERT INTO runtime_states VALUES (?,?) ON CONFLICT(run_id) "
                   "DO UPDATE SET data_json=excluded.data_json",
                   (state.run_id, json.dumps(payload)))


def load_state(path: Path | str, run_id: str) -> RuntimeState | None:
    with sqlite3.connect(path) as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                            "AND name='runtime_states'").fetchone()
        if not exists:
            return None
        row = db.execute("SELECT data_json FROM runtime_states WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        return None
    raw = json.loads(row[0])
    state = RuntimeState(raw["run_id"], raw["user_messages"], set(raw["allowed_origins"]))
    state.phase = raw["phase"]
    state.contract = GoalContract.model_validate(raw["contract"]) if raw["contract"] else None
    state.observations = {key: Observation.model_validate(value)
                          for key, value in raw["observations"].items()}
    state.facts = {key: Fact.model_validate(value) for key, value in raw["facts"].items()}
    state.source_values = raw["source_values"]
    state.policy = raw["policy"]
    state.approvals = [Approval.model_validate(value) for value in raw["approvals"]]
    state.pending = [PendingMutation.model_validate(value) for value in raw["pending"]]
    state.plan = raw["plan"]
    state.observations_text = raw["observations_text"]
    state.feedback = raw["feedback"]
    state.steps = raw["steps"]
    state.wrote_business_data = raw["wrote_business_data"]
    state.export_path = raw["export_path"]
    state.verify_rounds = raw["verify_rounds"]
    state.last_verification = raw.get("last_verification")
    return state
