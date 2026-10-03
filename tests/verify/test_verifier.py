import pytest

from tests.verify.util import FakeProbes
from worker.contracts import Criterion, GoalProposal, GoalType
from worker.verify.goals import commit_goal
from worker.verify.probes import CsvRows
from worker.verify.verifier import verify


@pytest.mark.asyncio
async def test_wrong_field_and_duplicate_prevent_completion():
    probes = FakeProbes()
    proposal = GoalProposal(goal_type=GoalType.register_invoice, supplier="Larkspur Supplies",
                            selector="latest")
    contract = await commit_goal(proposal, "Register latest from Larkspur Supplies", probes,
                                 run_id="r1")
    probes.registered = [{**probes.documents[1], "id": 4, "due_date": "2026-11-02"}]
    result = await verify(contract, probes)
    assert result.status == "failed"
    assert not next(check for check in result.checks if check.obligation_id == "record_fields").passed
    probes.registered = [probes.documents[1], probes.documents[1]]
    result = await verify(contract, probes)
    assert not next(check for check in result.checks if check.obligation_id == "record_count").passed


@pytest.mark.asyncio
async def test_empty_export_with_correct_header_can_complete():
    probes = FakeProbes()
    proposal = GoalProposal(goal_type=GoalType.export_invoices, due_before="2026-01-01")
    contract = await commit_goal(proposal, "Export invoices due before 2026-01-01",
                                 probes, run_id="r1")
    probes.csv["exports/empty.csv"] = CsvRows([], [
        "supplier_id", "invoice_number", "amount", "currency", "due_date",
    ])
    assert (await verify(contract, probes, export_path="exports/empty.csv")).status == "completed"


@pytest.mark.asyncio
async def test_batch_remaining_makes_partial_even_when_selected_saved():
    probes = FakeProbes()
    proposal = GoalProposal(goal_type=GoalType.register_batch, supplier="Larkspur Supplies",
                            selector="all_unregistered", max_count=1)
    contract = await commit_goal(proposal, "Register 1 unregistered invoice from Larkspur Supplies",
                                 probes, run_id="r1")
    probes.registered = [probes.documents[0]]
    result = await verify(contract, probes)
    assert result.status == "partial"
    assert result.remaining == ["LS-1042"]


@pytest.mark.asyncio
async def test_export_extra_or_missing_row_fails():
    probes = FakeProbes()
    probes.registered = [dict(probes.documents[0]), dict(probes.documents[1])]
    proposal = GoalProposal(goal_type=GoalType.export_invoices, due_before="2026-12-01")
    contract = await commit_goal(proposal, "Export invoices due before 2026-12-01",
                                 probes, run_id="r1")
    path = "exports/due.csv"
    columns = ("supplier_id", "invoice_number", "amount", "currency", "due_date")
    probes.csv[path] = [{key: probes.registered[0][key] for key in columns}]
    assert (await verify(contract, probes, export_path=path)).status == "failed"
    probes.csv[path].append({**{key: probes.registered[1][key] for key in columns},
                             "invoice_number": "EXTRA"})
    assert (await verify(contract, probes, export_path=path)).status == "failed"
    probes.csv[path] = [{key: row[key] for key in columns} for row in probes.registered]
    assert (await verify(contract, probes, export_path=path)).status == "completed"


@pytest.mark.asyncio
async def test_invalid_saved_amount_is_a_failed_check_not_a_crash():
    probes = FakeProbes()
    proposal = GoalProposal(goal_type=GoalType.register_invoice, supplier="Larkspur Supplies",
                            selector="latest")
    contract = await commit_goal(proposal, "Register latest from Larkspur Supplies", probes,
                                 run_id="r1")
    probes.registered = [{**probes.documents[1], "amount": "garbled"}]
    result = await verify(contract, probes)
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_extra_registered_probe_adds_a_real_check():
    probes = FakeProbes()
    proposal = GoalProposal(goal_type=GoalType.register_invoice, supplier="Larkspur Supplies",
                            selector="latest", extra_criteria=[Criterion(
                                probe="register_invoice",
                                where={"supplier_id": "larkspur-supplies", "invoice_number": "LS-1042"},
                                expect={"amount": "48250.00"})])
    contract = await commit_goal(proposal, "Register latest from Larkspur Supplies", probes,
                                 run_id="r1")
    probes.registered = [dict(probes.documents[1])]
    assert (await verify(contract, probes)).status == "completed"
    probes.registered[0]["amount"] = "48251.00"
    assert (await verify(contract, probes)).status == "failed"
