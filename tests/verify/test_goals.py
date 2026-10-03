import pytest

from tests.verify.util import FakeProbes
from worker.contracts import Criterion, GoalProposal, GoalType
from worker.verify.goals import GoalRejection, commit_goal, revise_goal


@pytest.mark.asyncio
async def test_latest_source_is_code_resolved_and_frozen():
    probes = FakeProbes()
    proposal = GoalProposal(goal_type=GoalType.register_invoice, supplier="Larkspur Supplies",
                            selector="latest", source_doc_id="ls-1042")
    result = await commit_goal(proposal, "Register the latest invoice from Larkspur Supplies",
                               probes, run_id="r1")
    assert result.sources[0].doc_id == "ls-1042"
    assert {item.kind for item in result.obligations} == {
        "supplier_resolved", "source_is_latest", "record_count", "record_fields",
    }
    assert [item.target_field for item in result.field_map] == [
        "invoice_number", "amount", "currency", "due_date",
    ]
    assert result.constraints.selector == "latest"
    assert result.obligations[-1].params["source_values"]["ls-1042"]["Amount"] == "48250.00"


@pytest.mark.asyncio
async def test_wrong_latest_and_material_request_change_are_rejected():
    probes = FakeProbes()
    wrong = GoalProposal(goal_type=GoalType.register_invoice, supplier="Larkspur Supplies",
                         selector="latest", source_doc_id="ls-1041")
    result = await commit_goal(wrong, "Register the latest invoice from Larkspur Supplies",
                               probes, run_id="r1")
    assert isinstance(result, GoalRejection)
    assert result.code == "source_mismatch"
    number = GoalProposal(goal_type=GoalType.register_invoice, supplier="Larkspur Supplies",
                          selector="invoice_number", invoice_number="LS-1042")
    result = await commit_goal(number, "Register the latest invoice from Larkspur Supplies",
                               probes, run_id="r1")
    assert result.code == "request_mismatch"


@pytest.mark.asyncio
async def test_ambiguous_supplier_and_tied_latest_ask_user():
    probes = FakeProbes()
    proposal = GoalProposal(goal_type=GoalType.register_invoice, supplier="Larkspur",
                            selector="latest")
    result = await commit_goal(proposal, "Register the latest invoice from Larkspur", probes, run_id="r1")
    assert result.code == "needs_clarification"
    assert len(result.candidates) == 2
    probes.documents[0]["issue_date"] = probes.documents[1]["issue_date"]
    exact = proposal.model_copy(update={"supplier": "Larkspur Supplies"})
    result = await commit_goal(exact, "Register the latest invoice from Larkspur Supplies", probes, run_id="r1")
    assert result.code == "needs_clarification"


@pytest.mark.asyncio
async def test_number_must_appear_in_request_and_batch_set_is_frozen():
    probes = FakeProbes()
    number = GoalProposal(goal_type=GoalType.check_or_register_invoice,
                          supplier="Larkspur Supplies", selector="invoice_number",
                          invoice_number="LS-1042")
    assert (await commit_goal(number, "Check Larkspur Supplies and add the invoice if missing", probes,
                              run_id="r1")).code == "request_mismatch"
    batch = GoalProposal(goal_type=GoalType.register_batch, supplier="Larkspur Supplies",
                         selector="all_unregistered", max_count=1)
    contract = await commit_goal(batch, "Register 1 unregistered invoice from Larkspur Supplies",
                                 probes, run_id="r1")
    assert [ref.key for ref in contract.sources] == ["LS-1041"]
    assert [ref.key for ref in contract.batch_remaining] == ["LS-1042"]
    probes.registered.append(probes.documents[0])
    assert [ref.key for ref in contract.sources] == ["LS-1041"]


@pytest.mark.asyncio
async def test_material_revision_requires_confirmation():
    probes = FakeProbes()
    initial = GoalProposal(goal_type=GoalType.register_invoice, supplier="Larkspur Supplies",
                           selector="latest")
    contract = await commit_goal(initial, "Register the latest invoice from Larkspur Supplies", probes,
                                 run_id="r1")
    revised = initial.model_copy(update={"selector": "invoice_number", "invoice_number": "LS-1042"})
    assert revise_goal(contract, revised, wrote_business_data=False).code == "confirmation_required"
    assert revise_goal(contract, initial, wrote_business_data=True).code == "locked_after_write"


@pytest.mark.asyncio
async def test_extra_criterion_must_have_registered_probe():
    probes = FakeProbes()
    proposal = GoalProposal(goal_type=GoalType.register_invoice, supplier="Larkspur Supplies",
                            selector="latest", extra_criteria=[Criterion(
                                probe="unknown", where={}, expect={"x": "y"})])
    result = await commit_goal(proposal, "Register the latest invoice from Larkspur Supplies", probes,
                               run_id="r1")
    assert result.code == "unsupported"
    original = GoalProposal(goal_type=GoalType.register_invoice, supplier="Larkspur Supplies",
                            selector="latest")
    contract = await commit_goal(original, "Register the latest invoice from Larkspur Supplies", probes,
                                 run_id="r1")
    assert revise_goal(contract, proposal, wrote_business_data=False).code == "unsupported"


@pytest.mark.asyncio
async def test_source_revision_change_during_commit_is_refused():
    class ChangingProbes(FakeProbes):
        async def portal_document(self, doc_id):
            doc = await super().portal_document(doc_id)
            return {**doc, "revision": "2"}

    proposal = GoalProposal(goal_type=GoalType.register_invoice, supplier="Larkspur Supplies",
                            selector="latest")
    result = await commit_goal(proposal, "Register the latest invoice from Larkspur Supplies",
                               ChangingProbes(), run_id="r1")
    assert result.code == "source_mismatch"


@pytest.mark.asyncio
async def test_check_or_register_requires_number_selector_and_freezes_existing_record():
    probes = FakeProbes()
    probes.registered = [{**probes.documents[1], "id": 7, "version": 3}]
    wrong = GoalProposal(goal_type=GoalType.check_or_register_invoice,
                         supplier="Larkspur Supplies", selector="latest",
                         invoice_number="LS-1042")
    assert (await commit_goal(wrong, "Check LS-1042 from Larkspur Supplies and add it if missing", probes,
                              run_id="r1")).code == "request_mismatch"
    valid = wrong.model_copy(update={"selector": "invoice_number"})
    contract = await commit_goal(valid, "Check LS-1042 from Larkspur Supplies and add it if missing", probes,
                                 run_id="r1")
    assert next(item for item in contract.obligations if item.kind == "no_write").params == {
        "record_id": "7", "version": "3",
    }
