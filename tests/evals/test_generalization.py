import csv
import sqlite3
from datetime import date

from evals.oracle import audit_snapshot, failure_category, inspect_case, score_understanding
from sandbox.portal.app import init_db as init_portal
from sandbox.register.db import init_db as init_register
from worker.contracts import Principal
from worker.store import Store


def _setup(tmp_path):
    portal, register = tmp_path / "portal.db", tmp_path / "register.db"
    init_portal(portal, date(2026, 10, 3))
    init_register(register, date(2026, 10, 3))
    store = Store(tmp_path / "worker.db")
    store.create_run("r1", "request", Principal(user_id="meera", email="meera@example.com",
                                                display_name="Meera", role="operator"), "fake")
    store.before = audit_snapshot(register)
    return portal, register, store


def _copy_invoice(portal, register, number):
    with sqlite3.connect(portal) as src:
        src.row_factory = sqlite3.Row
        row = dict(src.execute("SELECT * FROM invoices WHERE invoice_number=?", (number,)).fetchone())
    with sqlite3.connect(register) as db:
        db.execute("INSERT INTO invoices(supplier_id,invoice_number,amount,currency,due_date,"
                   "source_doc_id,created_by) VALUES (?,?,?,?,?,?,?)",
                   (row["supplier_id"], number, row["amount"], row["currency"], row["due_date"],
                    row["doc_id"], "meera"))


def _complete(store):
    store.append_event("r1", "verification", {"passed": True})
    store.update_run("r1", status="completed", phase="done")


def test_batch_checks_every_expected_invoice(tmp_path):
    portal, register, store = _setup(tmp_path)
    _copy_invoice(portal, register, "KC-702")
    _complete(store)
    case = {"id": "b", "expected_status": "completed", "principal": "meera",
            "expected_invoices": ["KC-702", "KC-703"]}
    result = inspect_case(case, store, "r1", portal, register, tmp_path / "ws", before=store.before)
    assert not result["success"] and result["false_completion"]
    _copy_invoice(portal, register, "KC-703")
    assert inspect_case(case, store, "r1", portal, register, tmp_path / "ws", before=store.before)["success"]


def test_export_accepts_any_single_csv_name(tmp_path):
    portal, register, store = _setup(tmp_path)
    _complete(store)
    exports = tmp_path / "ws" / "exports"
    exports.mkdir(parents=True)
    with sqlite3.connect(register) as db:
        rows = db.execute("SELECT supplier_id,invoice_number,amount,currency,due_date "
                          "FROM invoices WHERE due_date<?", ("2026-11-15",)).fetchall()
    with (exports / "whatever-they-chose.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["supplier_id", "invoice_number", "amount", "currency", "due_date"])
        writer.writerows(rows)
    case = {"id": "e", "expected_status": "completed", "expected_export": "any",
            "due_before": "2026-11-15"}
    assert inspect_case(case, store, "r1", portal, register, tmp_path / "ws", before=store.before)["export_correct"]


def test_supplier_contact_expectation(tmp_path):
    portal, register, store = _setup(tmp_path)
    _complete(store)
    case = {"id": "c", "expected_status": "completed", "principal": "meera", "expected_supplier": {
        "id": "kestrova-components", "contact_email": "arun@kestrova.example.com"}}
    assert not inspect_case(case, store, "r1", portal, register, tmp_path / "ws", before=store.before)["success"]
    with sqlite3.connect(register) as db:
        db.execute("UPDATE suppliers SET contact_email='arun@kestrova.example.com' "
                   "WHERE id='kestrova-components'")
    assert inspect_case(case, store, "r1", portal, register, tmp_path / "ws", before=store.before)["success"]


def _event(kind, **data):
    return type("E", (), {"type": kind, "data": data})()


def test_failure_categories_come_from_the_run_record():
    limit = [_event("run_status", status="blocked", reason="The run reached its step limit.")]
    assert failure_category("blocked", "completed", limit) == "step_limit"
    caught = [_event("verification", passed=False), _event("run_status", status="failed")]
    assert failure_category("failed", "completed", caught) == "verifier_caught"
    assert failure_category("awaiting_input", "completed", []) == "asked_instead"
    assert failure_category("unsupported", "completed", []) == "misread_request"
    assert failure_category("completed", "blocked", []) == "missed_refusal"


def test_understanding_scores_goal_fields_and_outcomes():
    expected = {"outcome": "committed", "goal_type": "register_batch",
                "supplier": "Kestrova Components", "max_count": 2}
    contract = {"goal_type": "register_batch", "supplier_name": "Kestrova Components",
                "constraints": {"cap": 2, "selector": "all_unregistered"}}
    assert score_understanding(expected, "committed", contract)["correct"]
    wrong = {**contract, "constraints": {"cap": 5}}
    scored = score_understanding(expected, "committed", wrong)
    assert not scored["correct"] and any("max_count" in item for item in scored["mismatch"])
    assert score_understanding({"outcome": "question"}, "question", None)["correct"]
    assert not score_understanding({"outcome": "unsupported"}, "committed", contract)["correct"]
