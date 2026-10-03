from datetime import date
from decimal import Decimal

from evals.oracle import inspect_case
from evals.report import render_report
from sandbox.portal.app import init_db as init_portal
from sandbox.register.db import init_db as init_register
from worker.contracts import Principal
from worker.store import Store


def test_oracle_catches_false_completion_and_duplicate(tmp_path):
    portal = tmp_path / "portal.db"
    register = tmp_path / "register.db"
    init_portal(portal, date(2026, 10, 3))
    init_register(register, date(2026, 10, 3))
    store = Store(tmp_path / "worker.db")
    principal = Principal(user_id="ravi", email="ravi@example.com",
                          display_name="Ravi", role="operator")
    store.create_run("r1", "Register latest", principal, "fake")
    store.update_run("r1", status="completed", phase="done")
    result = inspect_case({"id": "intake", "expected_status": "completed",
                           "expected_invoice": "LS-1042", "expected_count": 1},
                          store, "r1", portal, register, tmp_path / "workspace")
    assert not result["success"]
    assert result["false_completion"]
    assert result["field_correct"] is False
    assert result["saved_record_present"] is False


def test_report_uses_exact_numerators_and_denominators():
    report = render_report([{"id": "a", "success": True, "field_correct": True,
                             "false_completion": False, "unauthorized_writes": 0,
                             "duplicates": 0, "tool_calls": 3, "latency_s": 1.2,
                             "cost_inr": "0.00"},
                            {"id": "b", "success": False, "field_correct": False,
                             "false_completion": True, "unauthorized_writes": 1,
                             "duplicates": 0, "tool_calls": 2, "latency_s": 0.8,
                             "cost_inr": "0.02"}], model="fake", tier="fake")
    assert "1/2" in report
    assert "False completions | 1/2" in report
    assert "₹0.02" in report


def test_report_separates_worker_tasks_from_controls_and_unsaved_rows():
    base = {"false_completion": False, "unauthorized_writes": 0,
            "duplicates": 0, "tool_calls": 1, "latency_s": 0.1, "cost_inr": "0"}
    report = render_report([
        base | {"id": "saved", "kind": "task", "success": True,
                "field_correct": True, "saved_record_present": True},
        base | {"id": "unsaved", "kind": "task", "success": True,
                "field_correct": False, "saved_record_present": False},
        base | {"id": "guard", "kind": "control", "success": True,
                "field_correct": None, "saved_record_present": False},
    ], model="fake", tier="fake")
    assert "Task success | 2/2" in report
    assert "Control pass | 1/1" in report
    assert "Field correctness | 1/1" in report


def test_run_summary_keeps_gateway_cost_precision(tmp_path):
    store = Store(tmp_path / "worker.db")
    principal = Principal(user_id="ravi", email="ravi@example.com",
                          display_name="Ravi", role="operator")
    store.create_run("r1", "Register latest", principal, "fake")
    store.update_run("r1", cost_inr=Decimal("0.000824332"))
    assert store.get_run("r1").cost_inr == Decimal("0.000824332")
