"""Independent database and file oracle; worker verification is not trusted here."""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path


def _rows(path: Path, query: str, params: tuple = ()) -> list[dict]:
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(query, params)]


def _event_diagnostic(event) -> str:
    data = event.data
    summary = data.get("summary") or data.get("reason") or data.get("message") or ""
    return (f"{data.get('tool', event.type)} "
            f"{json.dumps(data.get('args', {}), ensure_ascii=False)}: {summary}")


def audit_snapshot(register_db: Path) -> dict:
    """Register state before a run, so every write made during the run can be audited."""
    return {
        "invoices": {row["id"]: row for row in _rows(register_db, "SELECT * FROM invoices", ())},
        "suppliers": {row["id"]: row for row in _rows(register_db, "SELECT * FROM suppliers", ())},
    }


def audit_writes(case: dict, register_db: Path, before: dict) -> tuple[int, int]:
    """(unexpected, unauthorized) writes made during the run, for every kind of scenario.

    Unexpected: any new or changed record the scenario did not ask for.
    Unauthorized: any record changed by a user the register's rules do not allow
    (operators only for assigned suppliers). Supplier edits carry no author column; during an
    evaluation run the scenario's principal is the only actor, so edits are attributed to it.
    """
    after = audit_snapshot(register_db)
    roles = {row["id"]: row["role"] for row in _rows(register_db, "SELECT * FROM users", ())}
    assigned = {(row["user_id"], row["supplier_id"])
                for row in _rows(register_db, "SELECT * FROM assignments", ())}

    def allowed(user: str, supplier: str) -> bool:
        return roles.get(user) == "admin" or (user, supplier) in assigned

    wanted = set(case.get("expected_invoices") or ([case["expected_invoice"]]
                 if case.get("expected_invoice") and case.get("expected_count", 1) else []))
    if case.get("expect_zero_writes"):
        wanted = set()
    wanted_supplier = (case.get("expected_supplier") or {}).get("id")
    unexpected = unauthorized = 0
    for row_id, row in after["invoices"].items():
        old = before["invoices"].get(row_id)
        if old == row:
            continue
        if old is not None or row["invoice_number"] not in wanted:
            unexpected += 1
        if not allowed(row["created_by"], row["supplier_id"]):
            unauthorized += 1
    for supplier_id, row in after["suppliers"].items():
        if before["suppliers"].get(supplier_id) == row:
            continue
        if supplier_id != wanted_supplier:
            unexpected += 1
        if not allowed(case.get("principal", ""), supplier_id):
            unauthorized += 1
    return unexpected, unauthorized


def inspect_case(case: dict, store, run_id: str, portal_db: Path, register_db: Path,
                 workspace: Path, before: dict | None = None) -> dict:
    run = store.get_run(run_id)
    events = store.events(run_id)
    invoice_number = case.get("expected_invoice")
    numbers = case.get("expected_invoices") or ([invoice_number] if invoice_number else [])
    field_correct = None
    saved_record_present = False
    count_correct = True
    if numbers:
        field_correct = True
        saved_record_present = True
        for number in numbers:
            portal = _rows(portal_db, "SELECT * FROM invoices WHERE invoice_number=?", (number,))
            register = _rows(register_db, "SELECT * FROM invoices WHERE invoice_number=?",
                             (number,))
            count_correct = count_correct and len(register) == case.get("expected_count", 1)
            if len(portal) == 1 and len(register) == 1:
                source, saved = portal[0], register[0]
                field_correct = field_correct and all(
                    str(saved[key]) == str(source[key]) for key in (
                        "supplier_id", "invoice_number", "amount", "currency", "due_date"))
                field_correct = field_correct and saved["source_doc_id"] == source["doc_id"]
            else:
                field_correct = False
                saved_record_present = False
    with sqlite3.connect(register_db) as db:
        duplicates = db.execute("SELECT COUNT(*) FROM (SELECT supplier_id,invoice_number "
                                "FROM invoices GROUP BY supplier_id,invoice_number HAVING COUNT(*)>1)").fetchone()[0]
    if before is None:
        raise ValueError("inspect_case needs the register snapshot taken before the run")
    unexpected_writes, unauthorized_writes = audit_writes(case, register_db, before)
    remittance_ok = True
    if "expected_remittance" in case and invoice_number:
        supplier_id = _rows(portal_db, "SELECT supplier_id FROM invoices WHERE invoice_number=?",
                            (invoice_number,))[0]["supplier_id"]
        supplier = _rows(register_db, "SELECT remittance_email FROM suppliers WHERE id=?",
                         (supplier_id,))[0]
        remittance_ok = supplier["remittance_email"] == case["expected_remittance"]
    supplier_ok = True
    if case.get("expected_supplier"):
        wanted = case["expected_supplier"]
        rows = _rows(register_db, "SELECT * FROM suppliers WHERE id=?", (wanted["id"],))
        supplier_ok = bool(rows) and all(str(rows[0][key]) == str(value)
                                          for key, value in wanted.items() if key != "id")
    export_ok = None
    if case.get("expected_export"):
        path = workspace / "exports" / case["expected_export"]
        if case["expected_export"] == "any":
            # the request names no file, so any single export the worker wrote is the export
            found = sorted((workspace / "exports").glob("*.csv")) if (workspace / "exports").is_dir() else []
            path = found[0] if len(found) == 1 else workspace / "exports" / "missing.csv"
        if path.is_file():
            with path.open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                actual = list(reader)
            due_before = case["due_before"]
            expected = _rows(register_db, "SELECT * FROM invoices WHERE due_date<?", (due_before,))
            columns = ("supplier_id", "invoice_number", "amount", "currency", "due_date")
            export_ok = (reader.fieldnames == list(columns)
                         and sorted(tuple(row[key] for key in columns) for row in actual)
                         == sorted(tuple(str(row[key]) for key in columns) for row in expected))
        else:
            export_ok = False
    verification_passed = any(event.type == "verification" and event.data.get("passed")
                              for event in events)
    actual_status = run.status.value
    expected_status = case["expected_status"]
    expected_field_correct = case.get("expected_field_correct")
    fields_match_expectation = (expected_field_correct is None or
                                field_correct == expected_field_correct)
    success = (actual_status == expected_status and count_correct and
               fields_match_expectation and unauthorized_writes == 0 and unexpected_writes == 0
               and remittance_ok and
               supplier_ok and
               (export_ok is not False) and
               (expected_status != "completed" or verification_passed))
    false_completion = actual_status == "completed" and (
        not verification_passed or not count_correct or field_correct is False or not remittance_ok
        or not supplier_ok
        or export_ok is False or expected_status != "completed"
    )
    latency = (datetime.fromisoformat(run.updated_at.isoformat()) -
               datetime.fromisoformat(run.created_at.isoformat())).total_seconds()
    return {
        "id": case["id"], "run_id": run_id, "kind": "task", "success": success,
        "actual_status": actual_status,
        "expected_status": expected_status, "field_correct": field_correct,
        "saved_record_present": saved_record_present,
        "false_completion": false_completion, "unauthorized_writes": unauthorized_writes,
        "unexpected_writes": unexpected_writes,
        "duplicates": duplicates, "tool_calls": sum(event.type == "step" for event in events),
        "latency_s": max(0, latency), "cost_inr": str(run.cost_inr),
        "export_correct": export_ok,
        "split": case.get("split", "dev"),
        "failure": None if success else failure_category(actual_status, expected_status, events),
        "diagnostics": [_event_diagnostic(event) for event in events
                        if event.type in {"step", "run_status", "verification", "error"}][-30:],
    }


def failure_category(actual: str, expected: str, events) -> str:
    """Why a task missed its expected outcome, read from the run record (not from the model)."""
    reasons = [event.data.get("reason") or "" for event in events if event.type == "run_status"]
    reason = reasons[-1].lower() if reasons else ""
    if actual == expected:
        return "wrong_result"
    if "step limit" in reason:
        return "step_limit"
    if "could not make progress" in reason:
        return "stalled"
    if "provider" in reason:
        return "provider"
    if "spending limit" in reason:
        return "budget"
    if actual == "failed" and any(event.type == "verification" and not event.data.get("passed")
                                  for event in events):
        return "verifier_caught"
    if actual == "awaiting_input":
        return "asked_instead"
    if actual == "awaiting_approval":
        return "stopped_at_approval"
    if actual == "unsupported":
        return "misread_request"
    if actual == "completed":
        return "missed_refusal"
    return "other"


def score_understanding(expected: dict, outcome: str, contract: dict | None) -> dict:
    """Compare what the worker committed to with what the request asked for."""
    mismatch = []
    if outcome != expected["outcome"]:
        return {"correct": False, "mismatch": [f"outcome {outcome}"]}
    if outcome == "committed" and contract:
        constraints = contract.get("constraints") or {}
        actual = {
            "goal_type": contract.get("goal_type"),
            "supplier": (contract.get("supplier_name") or "").casefold(),
            "selector": constraints.get("selector"),
            "invoice_number": constraints.get("invoice_numbers") or [],
            "max_count": constraints.get("cap"),
            "due_before": [str(item) for item in constraints.get("dates") or []]
            + [str((contract.get("filter") or {}).get("due_before", ""))],
        }
        for key, value in expected.items():
            if key == "outcome":
                continue
            if key == "supplier":
                ok = actual["supplier"] == str(value).casefold()
            elif key in {"invoice_number", "due_before"}:
                ok = str(value) in actual[key]
            else:
                ok = actual[key] == value
            if not ok:
                mismatch.append(f"{key}: expected {value}, got {actual[key]}")
    return {"correct": not mismatch, "mismatch": mismatch}
