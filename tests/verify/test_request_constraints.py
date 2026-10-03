from datetime import date

import pytest

from tests.verify.util import FakeProbes
from worker.verify.goals import commit_goal, dates_in, numbers_in


@pytest.mark.parametrize("text,expected", [
    ("Export invoices due before 2026-12-01.", date(2026, 12, 1)),
    ("due before 1 November 2026", date(2026, 11, 1)),
    ("due before 1 Nov 2026", date(2026, 11, 1)),
    ("due before November 1, 2026", date(2026, 11, 1)),
    ("due before 15/11/2026 (day first)", date(2026, 11, 15)),
    ("due before the 15th of November 2026", date(2026, 11, 15)),
])
def test_dates_in_reads_common_written_forms(text, expected):
    assert expected in dates_in(text.casefold())


def test_dates_in_ignores_impossible_dates():
    assert dates_in("due before 31/02/2026") == set()


@pytest.mark.parametrize("text,value", [
    ("at most 5 invoices", 5), ("up to three of them", 3), ("no more than two", 2),
    ("a maximum of ten", 10),
])
def test_numbers_in_reads_digits_and_words(text, value):
    assert value in numbers_in(text)


def test_numbers_in_does_not_invent_numbers():
    assert numbers_in("record every invoice we have not entered") == set()


class _MessageProbes:
    def __init__(self, messages):
        self.messages = messages

    async def register_suppliers(self):
        return [{"id": "kestrova-components", "name": "Kestrova Components", "aliases": ""}]

    async def portal_messages(self, supplier_id=None):
        return [row for row in self.messages if row["supplier_id"] == supplier_id]

    async def register_supplier(self, supplier_id):
        return {"id": supplier_id, "remittance_email": "old@kestrova.example.com"}

    async def portal_document(self, doc_id):
        return next(row for row in self.messages if row["doc_id"] == doc_id)


def _message(doc_id, day):
    return {"doc_id": doc_id, "revision": "1", "supplier_id": "kestrova-components",
            "date": day, "contact_name": "Arun Das", "contact_email": "a@kestrova.example.com",
            "remittance_email": "pay@kestrova.example.com"}


@pytest.mark.asyncio
async def test_contact_update_resolves_the_suppliers_latest_message_by_code():
    from worker.verify.goals import GoalRejection, commit_goal
    probes = _MessageProbes([_message("msg-old", "2026-09-01"), _message("msg-new", "2026-10-02")])
    contract = await commit_goal({"goal_type": "update_supplier_contact",
                                  "supplier": "Kestrova Components"},
                                 "Kestrova Components sent new contact details; update our record", probes, run_id="r")
    assert not isinstance(contract, GoalRejection)
    assert [source.doc_id for source in contract.sources] == ["msg-new"]
    tied = _MessageProbes([_message("a", "2026-10-02"), _message("b", "2026-10-02")])
    rejection = await commit_goal({"goal_type": "update_supplier_contact",
                                   "supplier": "Kestrova Components"},
                                  "Kestrova Components sent new contact details; update our record", tied, run_id="r")
    assert rejection.code == "needs_clarification" and set(rejection.candidates) == {"a", "b"}


@pytest.mark.asyncio
async def test_latest_request_cannot_carry_a_number_the_user_never_gave():
    from worker.verify.goals import commit_goal
    rejection = await commit_goal({"goal_type": "register_invoice", "supplier": "Kestrova Components",
                                   "invoice_number": "KC-703"},
                                  "Enter Kestrova Components' newest invoice",
                                  _MessageProbes([]), run_id="r")
    assert rejection.code == "request_mismatch"


@pytest.mark.asyncio
@pytest.mark.parametrize("proposal", [
    {"goal_type": "register_invoice", "supplier": "Larkspur Supplies",
     "invoice_number": "LS-1042"},
    {"goal_type": "register_invoice", "supplier": "Larkspur Supplies",
     "selector": "latest"},
])
async def test_explicit_invoice_number_cannot_be_replaced_by_a_different_source(proposal):
    result = await commit_goal(proposal, "Register invoice LS-1041 from Larkspur Supplies.",
                               FakeProbes(), run_id="r")
    assert result.code == "request_mismatch"


@pytest.mark.asyncio
async def test_negated_invoice_number_cannot_be_selected():
    result = await commit_goal(
        {"goal_type": "register_invoice", "supplier": "Larkspur Supplies",
         "invoice_number": "LS-1041"},
        "Add LS-1042 from Larkspur Supplies, but do not add LS-1041.",
        FakeProbes(), run_id="r")
    assert result.code in {"request_mismatch", "needs_confirmation"}


@pytest.mark.asyncio
async def test_after_date_cannot_be_committed_as_before_date():
    result = await commit_goal(
        {"goal_type": "export_invoices", "selector": "filter", "due_before": "2026-11-01"},
        "Export invoices due after 2026-11-01.", FakeProbes(), run_id="r")
    assert result.code in {"request_mismatch", "unsupported", "needs_confirmation"}


@pytest.mark.asyncio
async def test_export_cannot_drop_named_supplier_filter():
    result = await commit_goal(
        {"goal_type": "export_invoices", "selector": "filter", "due_before": "2026-11-01"},
        "Export invoices for Brightfen Paper due before 2026-11-01.",
        FakeProbes(), run_id="r")
    assert result.code in {"request_mismatch", "needs_confirmation"}


@pytest.mark.asyncio
async def test_export_cannot_drop_supplier_alias_filter():
    result = await commit_goal(
        {"goal_type": "export_invoices", "selector": "filter", "due_before": "2026-11-01"},
        "Export Brightfen invoices due before 2026-11-01.",
        FakeProbes(), run_id="r")
    assert result.code in {"request_mismatch", "needs_confirmation"}
