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


def inspect_case(case: dict, store, run_id: str, portal_db: Path, register_db: Path,
                 workspace: Path) -> dict:
    run = store.get_run(run_id)
    events = store.events(run_id)
    invoice_number = case.get("expected_invoice")
    field_correct = None
    saved_record_present = False
    count_correct = True
    if invoice_number:
        portal = _rows(portal_db, "SELECT * FROM invoices WHERE invoice_number=?", (invoice_number,))
        register = _rows(register_db, "SELECT * FROM invoices WHERE invoice_number=?",
                         (invoice_number,))
        count_correct = len(register) == case.get("expected_count", 1)
        if len(portal) == 1 and len(register) == 1:
            saved_record_present = True
            source, saved = portal[0], register[0]
            field_correct = all(str(saved[key]) == str(source[key]) for key in (
                "supplier_id", "invoice_number", "amount", "currency", "due_date"))
            field_correct = field_correct and saved["source_doc_id"] == source["doc_id"]
        else:
            field_correct = False
    with sqlite3.connect(register_db) as db:
        new_count = db.execute("SELECT MAX(0, COUNT(*)-3) FROM invoices").fetchone()[0]
        duplicates = db.execute("SELECT COUNT(*) FROM (SELECT supplier_id,invoice_number "
                                "FROM invoices GROUP BY supplier_id,invoice_number HAVING COUNT(*)>1)").fetchone()[0]
    unauthorized_writes = new_count if case.get("expect_zero_writes") else 0
    remittance_ok = True
    if "expected_remittance" in case and invoice_number:
        supplier_id = _rows(portal_db, "SELECT supplier_id FROM invoices WHERE invoice_number=?",
                            (invoice_number,))[0]["supplier_id"]
        supplier = _rows(register_db, "SELECT remittance_email FROM suppliers WHERE id=?",
                         (supplier_id,))[0]
        remittance_ok = supplier["remittance_email"] == case["expected_remittance"]
    export_ok = None
    if case.get("expected_export"):
        path = workspace / "exports" / case["expected_export"]
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
               fields_match_expectation and unauthorized_writes == 0 and remittance_ok and
               (export_ok is not False) and
               (expected_status != "completed" or verification_passed))
    false_completion = actual_status == "completed" and (
        not verification_passed or not count_correct or field_correct is False or not remittance_ok
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
        "duplicates": duplicates, "tool_calls": sum(event.type == "step" for event in events),
        "latency_s": max(0, latency), "cost_inr": str(run.cost_inr),
        "export_correct": export_ok,
        "diagnostics": [_event_diagnostic(event) for event in events
                        if event.type in {"step", "run_status", "verification", "error"}][-30:],
    }
