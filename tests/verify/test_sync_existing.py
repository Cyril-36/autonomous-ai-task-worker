"""A sixth goal: bring one existing register invoice back to its frozen portal source."""

import pytest

from tests.verify.util import FakeProbes
from worker.contracts import GoalType
from worker.verify.goals import commit_goal
from worker.verify.verifier import verify


@pytest.mark.asyncio
async def test_sync_existing_requires_named_invoice_and_existing_record():
    probes = FakeProbes()
    request = "Correct existing invoice LS-1041 from Larkspur Supplies to match the portal."
    proposal = {"goal_type": GoalType.sync_existing_invoice,
                "supplier": "Larkspur Supplies", "selector": "invoice_number",
                "invoice_number": "LS-1041"}
    missing = await commit_goal(proposal, request, probes, run_id="r1")
    assert missing.code == "blocked"
    probes.registered = [{**probes.documents[0], "id": 7, "version": 2,
                          "due_date": "2026-11-15"}]
    contract = await commit_goal(proposal, request, probes, run_id="r1")
    assert contract.goal_type == GoalType.sync_existing_invoice
    assert contract.sources[0].key == "LS-1041"
    assert any(item.kind == "approval_recorded" for item in contract.obligations)
    assert any(item.kind == "target_record" and item.params["record_id"] == "7"
               for item in contract.obligations)


@pytest.mark.asyncio
async def test_sync_existing_verifies_readback_and_approval():
    class ApprovedProbes(FakeProbes):
        approved = False

        async def approval_recorded(self, run_id):
            return self.approved

    probes = ApprovedProbes()
    probes.registered = [{**probes.documents[0], "id": 7, "version": 2,
                          "due_date": "2026-11-15"}]
    contract = await commit_goal(
        {"goal_type": "sync_existing_invoice", "supplier": "Larkspur Supplies",
         "selector": "invoice_number", "invoice_number": "LS-1041"},
        "Correct existing invoice LS-1041 from Larkspur Supplies to match the portal.",
        probes, run_id="r1")
    assert (await verify(contract, probes)).status == "failed"
    probes.registered[0]["due_date"] = probes.documents[0]["due_date"]
    probes.registered[0]["version"] = 3
    assert (await verify(contract, probes)).status == "failed"
    probes.approved = True
    assert (await verify(contract, probes)).status == "completed"


@pytest.mark.asyncio
async def test_sync_existing_rejects_user_supplied_date_as_source_authority():
    probes = FakeProbes()
    probes.registered = [{**probes.documents[0], "id": 7, "version": 1}]
    result = await commit_goal(
        {"goal_type": "sync_existing_invoice", "supplier": "Larkspur Supplies",
         "selector": "invoice_number", "invoice_number": "LS-1041"},
        "Change due date of LS-1041 from Larkspur Supplies to 2026-12-31.",
        probes, run_id="r1")
    assert result.code == "request_mismatch"
