from pathlib import Path

import pytest
import yaml

from worker.contracts import GoalType
from worker.verify.goals import action_matches

EVALS = Path(__file__).resolve().parents[2] / "evals"
UNSUPPORTED = {"unsupported"}


def _requests():
    """Every request in the three evaluation sets with the goal type it should allow."""
    pairs = []
    for case in yaml.safe_load((EVALS / "understanding.yaml").read_text())["scenarios"]:
        expect = case["expect"]
        if expect["outcome"] == "committed":
            goal = expect.get("goal_type", "register_invoice")
            pairs.append((case["request"], goal))
        elif expect["outcome"] == "unsupported":
            pairs.append((case["request"], None))
    return pairs


@pytest.mark.parametrize("request_text,goal", [p for p in _requests() if p[1]])
def test_supported_requests_match_their_goal_type(request_text, goal):
    assert action_matches(GoalType(goal), request_text)


@pytest.mark.parametrize("request_text", [p[0] for p in _requests() if p[1] is None] + [
    "Delete invoice LS-1039 from the register.",
    "Issue a refund to Larkspur Supplies for their last invoice.",
    "Approve every pending payment.",
])
def test_out_of_scope_actions_do_not_match_a_writing_goal(request_text):
    for goal in (GoalType.register_invoice, GoalType.register_batch,
                 GoalType.check_or_register_invoice, GoalType.update_supplier_contact):
        assert not action_matches(goal, request_text), goal


@pytest.mark.parametrize("request_text", [
    "Register the latest invoice from Larkspur Supplies",
    "Check or register BF-2291 from Brightfen Paper",
    "Register 1 unregistered invoice from Larkspur Supplies",
    "Pull Brightfen Paper's most recent bill off the supplier portal and log it in our register.",
    "Do we already have KC-701 from Kestrova Components on file? Only add it if it is missing.",
    "Bring Kestrova Components up to date in the register by recording any of their invoices we have not entered yet, at most 2.",
    "Kestrova Components sent us new contact details. Please update their supplier record to match.",
    "The newest invoice from Kestrova Components needs to go into the register.",
])
def test_development_and_heldout_wordings_are_accepted_by_some_goal(request_text):
    assert any(action_matches(goal, request_text) for goal in GoalType)


@pytest.mark.asyncio
async def test_commit_goal_refuses_a_goal_the_request_does_not_ask_for():
    from tests.verify.util import FakeProbes
    from worker.verify.goals import commit_goal
    rejection = await commit_goal(
        {"goal_type": "register_invoice", "supplier": "Larkspur Supplies", "selector": "latest"},
        "Issue a refund to Larkspur Supplies for their last invoice.", FakeProbes(), run_id="r")
    assert rejection.code == "request_mismatch"
    assert "unsupported" in rejection.reason


def test_a_check_only_request_cannot_become_a_goal_that_writes():
    assert not action_matches(GoalType.check_or_register_invoice,
                              "Check whether LS-1042 from Larkspur Supplies is registered")
    assert action_matches(GoalType.check_or_register_invoice,
                          "Is KC-702 in the register yet? If not, put it in.")
