from types import SimpleNamespace

from worker.contracts import (
    CheckResult,
    Fact,
    FactType,
    FieldMapping,
    GoalType,
    Obligation,
    RunStatus,
    SourceRef,
    VerificationResult,
)
from worker.runtime.apps import Apps
from worker.runtime.plan import goal_plan
from worker.verify.summary import describe_outcome

APPS = Apps.load({"portal": "http://p", "register": "http://r"})
SRC = SourceRef(kind="invoice", doc_id="ls-1042", revision="1", supplier_id="larkspur-supplies",
                key="LS-1042")
MAP = [FieldMapping(target_field="amount", source_label="Amount", type=FactType.amount),
       FieldMapping(target_field="due_date", source_label="Due date", type=FactType.date)]


def _contract(**extra):
    base = {"goal_type": GoalType.register_invoice, "supplier_name": "Larkspur Supplies",
            "supplier_id": "larkspur-supplies", "sources": [SRC], "batch_remaining": [],
            "field_map": MAP, "filter": None,
            "obligations": [Obligation(obligation_id="o", kind="record_fields", description="x")]}
    base.update(extra)
    return SimpleNamespace(**base)


def _fact(label, value, doc="ls-1042"):
    key = f"{doc}.{label.lower().replace(' ', '_')}"
    return key, Fact(key=key, value=value, normalized=value, type=FactType.text,
                     observation_id="o", url="u", doc_id=doc, revision="1", field_locator=label)


def _state(facts=(), committed=False, export_path=None):
    pending = [SimpleNamespace(state="committed", target_key={
        "supplier_id": "larkspur-supplies", "invoice_number": "LS-1042"})] if committed else []
    return SimpleNamespace(facts=dict(facts), pending=pending, export_path=export_path)


def test_plan_steps_come_from_the_goal_and_procedure():
    steps = goal_plan(_contract(), APPS, _state())
    assert [step["text"] for step in steps] == [
        "Read LS-1042 at portal.invoice", "Enter LS-1042 in register.new_invoice",
        "Check the result by reading it back"]
    assert [step["status"] for step in steps] == ["doing", "todo", "todo"]


def test_plan_progress_is_marked_from_evidence_only():
    facts = [_fact("Amount", "48250.00"), _fact("Due date", "2026-11-01")]
    assert [s["status"] for s in goal_plan(_contract(), APPS, _state(facts))] == [
        "done", "doing", "todo"]
    assert [s["status"] for s in goal_plan(_contract(), APPS, _state(facts, committed=True))] == [
        "done", "done", "doing"]
    assert all(s["status"] == "done" for s in goal_plan(
        _contract(), APPS, _state(facts, committed=True), verified=True))
    # a fact from another document does not complete the read step
    other = [_fact("Amount", "1.00", doc="ls-1041"), _fact("Due date", "2026-11-01", doc="ls-1041")]
    assert goal_plan(_contract(), APPS, _state(other))[0]["status"] == "doing"


def test_plan_for_export_and_check_only_goals():
    export = _contract(goal_type=GoalType.export_invoices, sources=[], field_map=[],
                       filter={"due_before": "2026-11-15"})
    assert goal_plan(export, APPS, _state(export_path="exports/x.csv"))[0]["status"] == "done"
    check = _contract(goal_type=GoalType.check_or_register_invoice, obligations=[
        Obligation(obligation_id="n", kind="no_write", description="unchanged")])
    assert goal_plan(check, APPS, _state())[0]["text"].startswith("Confirm LS-1042")


def _result(passed=True, remaining=()):
    checks = [CheckResult(obligation_id="a", description="Exactly one row", passed=True),
              CheckResult(obligation_id="b", description="Saved fields match", passed=passed)]
    return VerificationResult(run_id="r", contract_id="c", passed=passed, checks=checks,
                              status=RunStatus.completed if passed else RunStatus.failed,
                              summary="x", remaining=list(remaining))


def test_summary_says_what_was_saved_in_plain_words():
    facts = dict([_fact("Amount", "48250.00"), _fact("Due date", "2026-11-01")])
    text = describe_outcome(_contract(), facts, _result())
    assert text == ("Saved invoice from Larkspur Supplies to the register: LS-1042 "
                    "(₹48,250.00, due 1 Nov 2026). 2 of 2 checks passed on read-back.")


def test_summary_for_failure_check_only_export_and_batch():
    assert describe_outcome(_contract(), {}, _result(passed=False)).startswith(
        "Not done: Saved fields match.")
    check = _contract(obligations=[Obligation(obligation_id="n", kind="no_write",
                                              description="unchanged")])
    assert "already in the register" in describe_outcome(check, {}, _result())
    export = _contract(goal_type=GoalType.export_invoices, filter={"due_before": "2026-11-15"})
    assert describe_outcome(export, {}, _result(), export_path="exports/due.csv",
                            export_rows=6).startswith(
        "Exported 6 invoices due before 15 Nov 2026 to exports/due.csv.")
    extra = SourceRef(kind="invoice", doc_id="ls-1043", revision="1",
                      supplier_id="larkspur-supplies", key="LS-1043")
    batch = _contract(goal_type=GoalType.register_batch, batch_remaining=[extra])
    assert "Left for later because of the cap: LS-1043." in describe_outcome(batch, {}, _result())


def test_summary_for_source_backed_correction_names_the_existing_record():
    correction = _contract(goal_type=GoalType.sync_existing_invoice,
                           obligations=[Obligation(obligation_id="target", kind="target_record",
                                                   description="corrected")])
    assert describe_outcome(correction, {}, _result()).startswith(
        "Corrected existing invoice LS-1042 for Larkspur Supplies to match its portal source.")


def test_write_pages_that_take_a_record_id_get_it_from_the_goal():
    from worker.runtime.prompts import describe_goal
    sync = _contract(goal_type=GoalType.sync_existing_invoice, obligations=[
        Obligation(obligation_id="t", kind="target_record", description="same record",
                   params={"record_id": "7", "version": "1"})])
    assert "register.invoice_edit(id=7)" in describe_goal(sync, APPS)
    assert any("register.invoice_edit(id=7)" in step["text"]
               for step in goal_plan(sync, APPS, _state()))
