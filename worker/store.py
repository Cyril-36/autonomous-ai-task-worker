"""Durable run and event storage for the console and runtime."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from worker.contracts import PendingMutation, Principal, RunEvent, RunStatus, RunSummary


def utc_now() -> datetime:
    return datetime.now(UTC)


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "•••" if key in {"form_token", "password", "cookie", "api_key"}
                else _clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    return value


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, request TEXT NOT NULL, principal_json TEXT NOT NULL,
                    status TEXT NOT NULL, phase TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, steps INTEGER NOT NULL DEFAULT 0,
                    cost_inr TEXT NOT NULL DEFAULT '0.00', model TEXT NOT NULL,
                    contract_json TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL, seq INTEGER NOT NULL, ts TEXT NOT NULL,
                    type TEXT NOT NULL, data_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, seq)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, data_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pending (
                    mutation_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, data_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ledger (
                    entry_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, data_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS questions (
                    question_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, text TEXT NOT NULL,
                    answer TEXT, answered_by TEXT
                );
            """)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def create_run(self, run_id: str, request: str, principal: Principal, model: str) -> RunSummary:
        now = utc_now().isoformat().replace("+00:00", "Z")
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs(run_id,request,principal_json,status,phase,created_at,updated_at,model) VALUES (?,?,?,?,?,?,?,?)",
                (run_id, request, principal.model_dump_json(), RunStatus.queued.value,
                 "setup", now, now, model),
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> RunSummary | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            return None
        return RunSummary(
            run_id=row["run_id"], request=row["request"],
            principal=Principal.model_validate_json(row["principal_json"]),
            status=row["status"], phase=row["phase"], created_at=row["created_at"],
            updated_at=row["updated_at"], steps=row["steps"],
            cost_inr=Decimal(row["cost_inr"]), model=row["model"],
        )

    def list_runs(self) -> list[RunSummary]:
        with self.connect() as db:
            ids = [row[0] for row in db.execute("SELECT run_id FROM runs ORDER BY created_at DESC")]
        return [self.get_run(run_id) for run_id in ids]

    def update_run(self, run_id: str, *, status: str | None = None,
                   phase: str | None = None, steps: int | None = None,
                   cost_inr: Decimal | None = None) -> RunSummary:
        updates = {"updated_at": utc_now().isoformat().replace("+00:00", "Z")}
        if status is not None:
            updates["status"] = status
        if phase is not None:
            updates["phase"] = phase
        if steps is not None:
            updates["steps"] = steps
        if cost_inr is not None:
            updates["cost_inr"] = f"{cost_inr:.2f}"
        clause = ", ".join(f"{key}=?" for key in updates)
        with self.connect() as db:
            db.execute(f"UPDATE runs SET {clause} WHERE run_id=?", (*updates.values(), run_id))
        return self.get_run(run_id)

    def append_event(self, run_id: str, event_type: str, data: dict) -> RunEvent:
        clean = _clean(data)
        now = utc_now().isoformat().replace("+00:00", "Z")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute(
                "INSERT INTO events VALUES (?,?,?,?,?)",
                (run_id, seq, now, event_type, json.dumps(clean)),
            )
        return RunEvent(run_id=run_id, seq=seq, ts=now, type=event_type, data=clean)

    def events(self, run_id: str, after: int = 0) -> list[RunEvent]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq", (run_id, after)
            ).fetchall()
        return [RunEvent(run_id=row["run_id"], seq=row["seq"], ts=row["ts"],
                         type=row["type"], data=json.loads(row["data_json"])) for row in rows]

    def save_approval(self, approval_id: str, run_id: str, data: dict) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO approvals VALUES (?,?,?)",
                       (approval_id, run_id, json.dumps(_clean(data))))

    def save_pending(self, pending: PendingMutation) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO pending VALUES (?,?,?)",
                       (pending.mutation_id, pending.run_id, pending.model_dump_json()))

    def pending_for_run(self, run_id: str) -> list[PendingMutation]:
        with self.connect() as db:
            rows = db.execute("SELECT data_json FROM pending WHERE run_id=?", (run_id,)).fetchall()
        return [PendingMutation.model_validate_json(row[0]) for row in rows]

    def approvals(self, run_id: str) -> list[dict]:
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute(
                "SELECT data_json FROM approvals WHERE run_id=?", (run_id,)
            )]

    def save_question(self, question_id: str, run_id: str, text: str) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO questions(question_id,run_id,text) VALUES (?,?,?)",
                       (question_id, run_id, text))

    def question(self, run_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT question_id,text FROM questions WHERE run_id=? AND answer IS NULL",
                             (run_id,)).fetchone()
        return dict(row) if row else None

    def answer(self, question_id: str, text: str, by: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE questions SET answer=?,answered_by=? WHERE question_id=?",
                       (text, by, question_id))
