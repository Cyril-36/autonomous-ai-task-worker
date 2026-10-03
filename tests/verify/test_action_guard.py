from pathlib import Path

import pytest
import yaml

from worker.contracts import GoalType
from worker.verify.goals import CONFIRM_ACTION, action_evidence

EVALS = Path(__file__).resolve().parents[2] / "evals"
WRITING_GOALS = (GoalType.register_invoice, GoalType.register_batch,
                 GoalType.check_or_register_invoice, GoalType.update_supplier_contact)


def _understanding():
    cases = yaml.safe_load((EVALS / "understanding.yaml").read_text())["scenarios"]
    return [(case["request"], case["expect"]) for case in cases]


@pytest.mark.parametrize("request_text,expect", [
    pair for pair in _understanding() if pair[1]["outcome"] == "committed"])
def test_supported_requests_are_clear_for_their_goal(request_text, expect):
    goal = GoalType(expect.get("goal_type", "register_invoice"))
    assert action_evidence(goal, request_text) == "clear"


@pytest.mark.parametrize("request_text", [
    request for request, expect in _understanding() if expect["outcome"] == "unsupported"] + [
    "Delete invoice LS-1039 from the register.",
    "Approve every pending payment.",
    "Do not record the latest invoice from Larkspur Supplies.",
    "Please don't register LS-1042 from Larkspur Supplies.",
])
def test_out_of_scope_or_negated_requests_give_no_evidence(request_text):
    for goal in WRITING_GOALS:
        assert action_evidence(goal, request_text) == "none", goal


@pytest.mark.parametrize("request_text", [
    "Record a refund for Larkspur Supplies' last invoice.",
    "Enter a credit note against invoice LS-1042.",
])
def test_an_action_on_some_other_object_is_unclear_and_must_be_confirmed(request_text):
    assert action_evidence(GoalType.register_invoice, request_text) == "unclear"


def test_a_check_only_request_must_be_confirmed_before_a_goal_that_writes():
    goal = GoalType.check_or_register_invoice
    assert action_evidence(goal, "Do we already have BF-2291 on file from Brightfen Paper?") == "unclear"
    assert action_evidence(goal, "Is LS-1042 from Larkspur Supplies in the register yet?") == "unclear"
    assert action_evidence(goal, "Is KC-702 in the register yet? If not, put it in.") == "clear"


@pytest.mark.parametrize("goal", [GoalType.register_invoice, GoalType.check_or_register_invoice])
def test_register_status_question_is_not_write_permission(goal):
    assert action_evidence(goal, "Is LS-1042 from Larkspur Supplies in the register yet?") == "unclear"
    assert action_evidence(goal, "Does LS-1042 need to go into the register?") == "unclear"
    assert action_evidence(goal, "Should I register invoice LS-1042?") == "unclear"
    assert action_evidence(goal, "The newest invoice needs to go into the register.") == "clear"


@pytest.mark.parametrize("goal", [GoalType.register_invoice, GoalType.check_or_register_invoice])
def test_explicit_no_write_still_wins_over_a_register_status_question(goal):
    request = ("Do not register LS-1042 from Larkspur Supplies. "
               "Just check whether LS-1042 is in the register.")
    assert action_evidence(goal, request) == "none"


@pytest.mark.parametrize("request_text", [
    "The latest invoice does not need to go into the register.",
    "The latest invoice doesn't need to go into the register.",
    "No invoice needs to go into the register.",
])
def test_negated_passive_request_never_authorizes_a_write(request_text):
    assert action_evidence(GoalType.register_invoice, request_text) == "none"


def test_instruction_to_ask_first_does_not_authorize_the_write():
    assert action_evidence(GoalType.register_invoice,
                           "Before you register invoice LS-1042, ask me first.") == "unclear"


def test_long_distance_negation_and_parentheses_block_registration():
    for request_text in (
        "Do not under any circumstances register the latest invoice from Larkspur Supplies.",
        "Do not (under any circumstances) register the latest invoice from Larkspur Supplies.",
    ):
        assert action_evidence(GoalType.register_invoice, request_text) == "none"


@pytest.mark.parametrize("request_text", [
    "Record a refund for invoice LS-1042 and put it in the register.",
    "Cancel invoice LS-1042 and record it as void.",
])
def test_unsupported_object_cannot_become_an_invoice_write(request_text):
    assert action_evidence(GoalType.register_invoice, request_text) != "clear"


def test_negation_in_another_clause_does_not_cancel_a_positive_invoice_request():
    assert action_evidence(GoalType.register_invoice,
                           "Don't export; just register the latest invoice from Larkspur Supplies.") == "clear"


@pytest.mark.asyncio
async def test_commit_goal_requires_confirmation_for_check_only_and_refuses_explicit_no_write():
    from tests.verify.util import FakeProbes
    from worker.verify.goals import commit_goal
    goal = {"goal_type": "register_invoice", "supplier": "Larkspur Supplies",
            "selector": "invoice_number", "invoice_number": "LS-1042"}
    check_only = await commit_goal(goal, "Is LS-1042 from Larkspur Supplies in the register yet?",
                                   FakeProbes(), run_id="r")
    assert check_only.code == "needs_confirmation"
    no_write = await commit_goal(
        goal, "Do not register LS-1042 from Larkspur Supplies. "
              "Just check whether LS-1042 is in the register.", FakeProbes(), run_id="r")
    assert no_write.code == "request_mismatch"


def test_confirming_answers_are_clear_evidence_for_their_goal():
    for goal, phrase in CONFIRM_ACTION.items():
        assert action_evidence(goal, f"Yes, {phrase}") == "clear", goal


@pytest.mark.parametrize("request_text", [
    "Register the latest invoice from Larkspur Supplies",
    "Check or register BF-2291 from Brightfen Paper",
    "Register 1 unregistered invoice from Larkspur Supplies",
    "Pull Brightfen Paper's most recent bill off the supplier portal and log it in our register.",
    "Do we already have KC-701 from Kestrova Components on file? Only add it if it is missing.",
    "Bring Kestrova Components up to date in the register by recording any of their invoices we have not entered yet, at most 2.",
    "Kestrova Components sent us new contact details. Please update their supplier record to match.",
    "The newest invoice from Kestrova Components needs to go into the register.",
    "Please add invoice LL-312 from Larkspur Logistics to the register.",
])
def test_development_and_heldout_wordings_are_clear_for_some_goal(request_text):
    assert "clear" in {action_evidence(goal, request_text) for goal in GoalType}


@pytest.mark.asyncio
async def test_commit_goal_refuses_none_and_asks_to_confirm_unclear():
    from tests.verify.util import FakeProbes
    from worker.verify.goals import commit_goal
    goal = {"goal_type": "register_invoice", "supplier": "Larkspur Supplies", "selector": "latest"}
    refused = await commit_goal(goal, "Issue a refund to Larkspur Supplies for their last invoice.",
                                FakeProbes(), run_id="r")
    assert refused.code == "request_mismatch" and "unsupported" in refused.reason
    unclear = await commit_goal(goal, "Record a refund for Larkspur Supplies' latest invoice.",
                                FakeProbes(), run_id="r")
    assert unclear.code == "needs_confirmation"
    assert unclear.candidates == [f"Yes, {CONFIRM_ACTION[GoalType.register_invoice]}", "No"]


def test_an_elliptical_request_is_confirmed_rather_than_guessed():
    assert action_evidence(GoalType.register_invoice,
                           "Register latest from Larkspur Supplies") == "unclear"
