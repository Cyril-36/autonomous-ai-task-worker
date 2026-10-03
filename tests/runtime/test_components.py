import json
from types import SimpleNamespace

import pytest

from worker.contracts import (
    Element,
    FactType,
    FieldMapping,
    GoalType,
    Obligation,
    Observation,
    SourceRef,
)
from worker.runtime.apps import Apps
from worker.runtime.loop import action_line, find_by_label, ready_to_finish
from worker.runtime.prompts import build_messages
from worker.runtime.stall import StallDetector
from worker.tools.registry import TOOLS, tools_for_phase, validate_call
from worker.trace.writer import TraceWriter

APPS = Apps.load({"portal": "http://127.0.0.1:9001", "register": "http://127.0.0.1:9002"})


def test_tool_registry_rejects_unknown_and_bad_args():
    assert validate_call("browser_click", {"ref": "e1"}) == {"ref": "e1"}
    with pytest.raises(ValueError):
        validate_call("browser_click", {"ref": "e1", "script": "alert(1)"})
    with pytest.raises(ValueError):
        validate_call("shell", {"cmd": "ls"})
    goal_tool = next(item for item in TOOLS if item["function"]["name"] == "commit_goal")
    contract = goal_tool["function"]["parameters"]["properties"]["contract"]
    assert "register_invoice" in contract["properties"]["goal_type"]["enum"]


def _names(**kwargs) -> set[str]:
    return {item["function"]["name"] for item in tools_for_phase(**kwargs)}


def test_model_gets_task_level_tools_not_low_level_ones():
    execute = _names(phase="execute")
    assert {"open_page", "record_facts", "fill_form", "submit_form", "finish"} <= execute
    assert not execute & {"browser_navigate", "browser_fill", "browser_fill_fact", "record_fact",
                          "browser_select", "commit_goal", "revise_goal"}
    assert "commit_goal" in _names(phase="discover")
    assert "revise_goal" in _names(phase="execute", allow_revision=True)
    assert _names(phase="execute", ready_to_verify=True) == {"finish"}
    assert _names(phase="execute", approved_form_pending=True) == {
        "submit_form", "browser_snapshot", "ask_user"}


def _contract(goal_type: GoalType, **extra):
    base = {"goal_type": goal_type, "supplier_name": None, "sources": [], "batch_remaining": [],
            "filter": None, "field_map": [], "obligations": [Obligation(
                obligation_id="o", kind="extra", description="A check")]}
    base.update(extra)
    return SimpleNamespace(**base)


def test_instructions_and_tools_are_identical_for_every_goal_type():
    """Generalization: only the locked goal's data differs between task types."""
    source = SourceRef(kind="invoice", doc_id="doc_a", revision="1", supplier_id="s", key="A-1")
    contracts = [
        _contract(GoalType.register_invoice, supplier_name="Some Supplier", sources=[source],
                  field_map=[FieldMapping(target_field="amount", source_label="Amount",
                                          type=FactType.amount)]),
        _contract(GoalType.export_invoices, filter={"due_before": "2026-11-01"}),
        _contract(GoalType.update_supplier_contact, supplier_name="Other", sources=[source]),
    ]
    systems, tools = set(), set()
    for contract in contracts:
        messages = build_messages("do it", phase="execute", contract=contract, observations=[],
                                  facts=[], plan=[], apps=APPS)
        systems.add(messages[0]["content"] + messages[1]["content"])
        tools.add(json.dumps(tools_for_phase("execute", contract=contract)))
    assert len(systems) == 1 and len(tools) == 1


def test_prompt_has_no_routes_hosts_or_example_records():
    contract = _contract(GoalType.register_invoice, supplier_name="Some Supplier")
    rendered = json.dumps(build_messages("do it", phase="execute", contract=contract,
                                         observations=[], facts=[], plan=[], apps=APPS))
    for leak in ("127.0.0.1", "/invoices", "Larkspur", "LS-1042", "Brightfen", "Total"):
        assert leak not in rendered
    assert "register.new_invoice" in rendered and "portal.invoice(id" in rendered


def test_prompt_marks_pages_untrusted_keeps_last_three_and_shows_action_log():
    observations = [f"Page {index}" for index in range(5)]
    messages = build_messages("Register latest invoice", phase="discover", contract=None,
                              observations=observations, facts=[], plan=[],
                              feedback=["#1 open_page {} -> ok: Opened 'Invoices'"], apps=APPS)
    rendered = json.dumps(messages)
    assert "<untrusted_page>Page 4</untrusted_page>" in rendered
    assert "<untrusted_page>Page 2</untrusted_page>" in rendered
    assert "<untrusted_page>Page 0</untrusted_page>" not in rendered
    assert "Your recent actions" in rendered and "#1 open_page" in rendered


def _observation(*elements):
    return Observation(observation_id="o1", run_id="r", step=1, url="http://x", title="Form",
                       text="", elements=list(elements), content_hash="h")


def test_find_by_label_matches_text_fields_and_selects_by_visible_label():
    form = _observation(
        Element(ref="e1", role="combobox", name="Supplier Alpha Ltd Beta Ltd",
                options=["Alpha Ltd", "Beta Ltd"]),
        Element(ref="e2", role="textbox", name="Invoice number"),
        Element(ref="e3", role="date", name="Payment due:"),
        Element(ref="e4", role="button", name="Save", submits_form=True),
    )
    assert find_by_label(form, "supplier").ref == "e1"
    assert find_by_label(form, "Invoice Number").ref == "e2"
    assert find_by_label(form, "Payment due").ref == "e3"
    with pytest.raises(ValueError, match="Fields here"):
        find_by_label(form, "Amount")
    with pytest.raises(ValueError):
        find_by_label(form, "Save")


def test_find_by_label_refuses_ambiguous_labels():
    form = _observation(Element(ref="e1", role="textbox", name="Contact email"),
                        Element(ref="e2", role="textbox", name="Contact email"))
    with pytest.raises(ValueError, match="several"):
        find_by_label(form, "Contact email")


def test_action_line_is_compact_and_hides_observation_ids():
    line = action_line(7, "record_facts", {"labels": ["Amount"], "observation_id": "abc"},
                       {"ok": False, "summary": "None of those labels are on this document."})
    assert line.startswith("#7 record_facts") and "FAILED" in line and "abc" not in line


def test_stall_requires_verified_progress():
    detector = StallDetector()
    assert detector.observe("browser_snapshot", {}, progress=False) is None
    assert detector.observe("browser_snapshot", {}, progress=False) is None
    assert detector.observe("browser_snapshot", {}, progress=False) == "reflect"
    detector.observe("browser_snapshot", {}, progress=True)
    assert detector.observe("browser_snapshot", {}, progress=False) is None


def test_ready_to_finish_requires_every_selected_source_to_be_committed():
    sources = [SimpleNamespace(kind="invoice", supplier_id="s1", key="A"),
               SimpleNamespace(kind="invoice", supplier_id="s1", key="B")]
    contract = SimpleNamespace(sources=sources)
    pending = [SimpleNamespace(state="committed", target_key={
        "supplier_id": "s1", "invoice_number": "A"})]
    state = SimpleNamespace(contract=contract, pending=pending, export_path=None,
                            verify_rounds=0, phase="execute")
    assert not ready_to_finish(state)
    pending.append(SimpleNamespace(state="committed", target_key={
        "supplier_id": "s1", "invoice_number": "B"}))
    assert ready_to_finish(state)
    state.verify_rounds = 1
    assert not ready_to_finish(state)


def test_trace_is_append_only_and_redacts_secrets(tmp_path):
    writer = TraceWriter(tmp_path, "r1", model="fake", base_url="local",
                         parameters={"max_tokens": 256}, prompt_hash="abc")
    writer.append("tool", {"name": "browser_click", "form_token": "secret"})
    lines = (tmp_path / "r1.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert "secret" not in "\n".join(lines)
    assert json.loads(lines[0])["model"] == "fake"
