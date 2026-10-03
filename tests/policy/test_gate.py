import pytest

from tests.policy.util import intent, state
from worker.contracts import FileWriteIntent, FillSource, GoalType, PendingMutation
from worker.policy.approvals import create_approval
from worker.policy.gate import check_file_write, check_mutation


def test_matching_source_facts_allow_invoice_write():
    decision = check_mutation(state(), intent())
    assert decision.allowed and decision.code == "allowed"


@pytest.mark.parametrize(("change", "code"), [
    (lambda s, i: setattr(s, "phase", "discover"), "phase_discover"),
    (lambda s, i: setattr(s, "contract", None), "no_contract"),
    (lambda s, i: setattr(s, "allowed_origins", set()), "origin_blocked"),
    (lambda s, i: setattr(s, "pending", [PendingMutation(
        mutation_id="old", run_id="r1", form_token="old", target_key=i.target_key,
        before_values=None, before_version=None, intended_values={}, state="dispatching")]),
     "pending_unresolved"),
])
def test_gate_refusal_codes_for_state(change, code):
    context = state()
    mutation = intent()
    change(context, mutation)
    assert check_mutation(context, mutation).code == code


def test_gate_rejects_wrong_source_wrong_fact_and_wrong_field_value():
    context = state()
    context.facts["due_date"] = context.facts["due_date"].model_copy(update={
        "value": "3 Oct 2026", "normalized": "2026-10-03", "field_locator": "Issue date",
    })
    mutation = intent().model_copy(update={"fields": {**intent().fields, "due_date": "2026-10-03"}})
    assert check_mutation(context, mutation).code == "field_mismatch"
    context = state()
    mutation = intent().model_copy(update={"source": intent().source.model_copy(update={"revision": "2"})})
    assert check_mutation(context, mutation).code == "source_mismatch"
    mutation = intent().model_copy(update={"filled_from": {**intent().filled_from,
        "amount": FillSource(kind="free_text")}})
    assert check_mutation(context, mutation).code == "provenance_failed"


def test_large_amount_requires_approval():
    context = state()
    context.policy["threshold"] = "40000.00"
    assert check_mutation(context, intent()).code == "needs_approval"
    context.approvals = [create_approval(intent(), "threshold", 1)]
    assert check_mutation(context, intent()).code == "approval_invalid"


def test_file_export_checks_path_and_query():
    context = state()
    context.contract = context.contract.model_copy(update={
        "goal_type": GoalType.export_invoices, "filter": {"due_before": "2026-10-31"},
    })
    write = FileWriteIntent(mutation_id="f1", run_id="r1", path="exports/report.csv",
                            probe_query={"due_before": "2026-10-31"})
    assert check_file_write(context, write).allowed
    assert check_file_write(context, write.model_copy(update={"path": "../bad.csv"})).code == "filename_invalid"
    assert check_file_write(context, write.model_copy(update={"probe_query": {}})).code == "query_mismatch"


def test_non_mutation_and_blocked_path_codes():
    context = state()
    assert check_mutation(context, intent().model_copy(update={"action_url":
        "http://127.0.0.1:8102/api/invoices"})).code == "path_blocked"
    assert check_mutation(context, intent().model_copy(update={"form_token": None})).code == "not_a_mutation"
    assert check_mutation(context, intent().model_copy(update={"action_url":
        "http://127.0.0.1:8102/policy"})).code == "path_blocked"
    context.policy["threshold"] = "999999.00"
    update = intent().model_copy(update={
        "action_url": "http://127.0.0.1:8102/invoices/4", "target_version": 1,
    })
    assert check_mutation(context, update).code == "needs_approval"
