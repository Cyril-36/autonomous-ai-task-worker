"""Persist budget reservations before provider dispatch and settle from gateway usage."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from worker.config import Pricing
from worker.contracts import LedgerEntry

MILLION = Decimal(1_000_000)
MARGIN = Decimal("1.20")


class BudgetExceeded(Exception):
    """The estimated local spending limit refused a provider call."""


class Ledger:
    def __init__(self, path: Path | str, pricing: Pricing):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.pricing = pricing
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS ledger (entry_id TEXT PRIMARY KEY, "
                       "run_id TEXT NOT NULL, data_json TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS ledger_model_bounds ("
                       "model TEXT PRIMARY KEY, observed_completion INTEGER NOT NULL DEFAULT 0, "
                       "max_tokens_enforced INTEGER NOT NULL DEFAULT 1)")
            db.execute("CREATE TABLE IF NOT EXISTS ledger_requests ("
                       "entry_id TEXT PRIMARY KEY, max_tokens INTEGER NOT NULL)")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def entries(self, run_id: str | None = None) -> list[LedgerEntry]:
        with self._connect() as db:
            if run_id:
                rows = db.execute("SELECT data_json FROM ledger WHERE run_id=?", (run_id,)).fetchall()
            else:
                rows = db.execute("SELECT data_json FROM ledger").fetchall()
        return [LedgerEntry.model_validate_json(row[0]) for row in rows]

    def spent(self, run_id: str | None = None) -> Decimal:
        return sum((entry.settled_inr if entry.settled_inr is not None
                    else entry.reserved_inr for entry in self.entries(run_id)), Decimal(0))

    def estimate(self, model: str, request: dict) -> Decimal:
        if model not in self.pricing.models:
            raise ValueError(f"No price configured for model {model}")
        price = self.pricing.models[model]
        serialized = json.dumps(request, ensure_ascii=False, separators=(",", ":"))
        messages = request.get("messages", [])
        input_bound = len(serialized.encode("utf-8")) + 8 * len(messages)
        max_tokens = request.get("max_tokens")
        if not isinstance(max_tokens, int) or max_tokens < 1:
            raise ValueError("Every provider call requires positive max_tokens")
        with self._connect() as db:
            row = db.execute("SELECT observed_completion,max_tokens_enforced "
                             "FROM ledger_model_bounds WHERE model=?", (model,)).fetchone()
        output_bound = max_tokens
        if row and not row["max_tokens_enforced"]:
            output_bound = max(output_bound, row["observed_completion"] * 2)
        return MARGIN * (
            Decimal(input_bound) * price.input_per_million
            + Decimal(output_bound) * price.output_per_million
        ) / MILLION

    def reserve(self, run_id: str, model: str, request: dict) -> LedgerEntry:
        estimate = self.estimate(model, request)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT run_id,data_json FROM ledger").fetchall()
            entries = [(row["run_id"], LedgerEntry.model_validate_json(row["data_json"]))
                       for row in rows]
            all_cost = sum((entry.settled_inr if entry.settled_inr is not None
                            else entry.reserved_inr for _, entry in entries), Decimal(0))
            run_cost = sum((entry.settled_inr if entry.settled_inr is not None
                            else entry.reserved_inr for owner, entry in entries if owner == run_id),
                           Decimal(0))
            if (all_cost + estimate > self.pricing.global_limit_inr or
                    run_cost + estimate > self.pricing.run_limit_inr):
                raise BudgetExceeded("Estimated local spending limit reached")
            entry = LedgerEntry(entry_id=uuid4().hex, run_id=run_id, model=model,
                                reserved_inr=estimate, state="reserved",
                                created_at=datetime.now(UTC))
            db.execute("INSERT INTO ledger VALUES (?,?,?)",
                       (entry.entry_id, run_id, entry.model_dump_json()))
            db.execute("INSERT INTO ledger_requests VALUES (?,?)",
                       (entry.entry_id, request["max_tokens"]))
        return entry

    def settle(self, entry_id: str, usage: dict | None) -> LedgerEntry:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data_json FROM ledger WHERE entry_id=?", (entry_id,)).fetchone()
            if row is None:
                raise KeyError(entry_id)
            entry = LedgerEntry.model_validate_json(row[0])
            if entry.state != "reserved":
                return entry
            if usage is None or usage.get("prompt_tokens") is None or usage.get("completion_tokens") is None:
                updated = entry.model_copy(update={"state": "charged_unknown",
                                                    "settled_inr": entry.reserved_inr})
            else:
                prompt = int(usage["prompt_tokens"])
                completion = int(usage["completion_tokens"])
                reported = usage.get("cost")
                if reported is None:
                    reported = usage.get("cost_inr")
                if reported is not None:
                    cost = Decimal(str(reported))
                else:
                    price = self.pricing.models[entry.model]
                    unaccounted = max(0, int(usage.get("total_tokens") or 0) - prompt - completion)
                    cost = (Decimal(prompt) * price.input_per_million
                            + Decimal(completion + unaccounted) * price.output_per_million) / MILLION
                updated = entry.model_copy(update={"state": "settled", "settled_inr": cost,
                                                    "prompt_tokens": prompt,
                                                    "completion_tokens": completion})
                request_row = db.execute("SELECT max_tokens FROM ledger_requests WHERE entry_id=?",
                                         (entry_id,)).fetchone()
                effective_output = max(completion,
                                       int(usage.get("total_tokens") or 0) - prompt)
                if request_row and effective_output > request_row[0]:
                    self._observe_overrun(db, entry.model, effective_output)
            db.execute("UPDATE ledger SET data_json=? WHERE entry_id=?",
                       (updated.model_dump_json(), entry_id))
        return updated

    @staticmethod
    def _observe_overrun(db, model: str, completion: int) -> None:
        db.execute("INSERT INTO ledger_model_bounds VALUES (?,?,0) "
                   "ON CONFLICT(model) DO UPDATE SET observed_completion="
                   "MAX(observed_completion,excluded.observed_completion), "
                   "max_tokens_enforced=0", (model, completion))
