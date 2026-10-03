import json
from types import SimpleNamespace

import pytest

from worker.contracts import GoalType
from worker.runtime.loop import ready_to_finish
from worker.runtime.prompts import build_messages
from worker.runtime.stall import StallDetector
from worker.tools.registry import TOOLS, tools_for_phase, validate_call
from worker.trace.writer import TraceWriter


def test_tool_registry_rejects_unknown_and_bad_args():
    assert {item["function"]["name"] for item in TOOLS} >= {
        "browser_snapshot", "browser_click", "commit_goal", "finish", "record_fact",
    }
    assert validate_call("browser_click", {"ref": "e1"}) == {"ref": "e1"}
    with pytest.raises(ValueError):
        validate_call("browser_click", {"ref": "e1", "script": "alert(1)"})
    with pytest.raises(ValueError):
        validate_call("shell", {"cmd": "ls"})
    fact_tool = next(item for item in TOOLS if item["function"]["name"] == "record_fact")
    assert fact_tool["function"]["parameters"]["properties"]["type"]["enum"] == [
        "text", "amount", "date",
    ]
    assert "enum" not in fact_tool["function"]["parameters"]["properties"]["key"]
    goal_tool = next(item for item in TOOLS if item["function"]["name"] == "commit_goal")
    contract = goal_tool["function"]["parameters"]["properties"]["contract"]
    assert "goal_type" in contract["required"]
    assert "register_invoice" in contract["properties"]["goal_type"]["enum"]
    assert any(item["function"]["name"] == "commit_goal"
               for item in tools_for_phase("discover"))
    assert not any(item["function"]["name"] == "commit_goal"
                   for item in tools_for_phase("execute"))
    assert not any(item["function"]["name"] == "revise_goal"
                   for item in tools_for_phase("execute"))
    assert any(item["function"]["name"] == "revise_goal"
               for item in tools_for_phase("execute", allow_revision=True))
    names = {item["function"]["name"] for item in tools_for_phase("execute")}
    assert {"browser_fill_fact", "browser_fill_text"} <= names
    assert "browser_fill" not in names
    assert [item["function"]["name"] for item in tools_for_phase(
        "execute", ready_to_verify=True)] == ["finish"]
    approved_names = {item["function"]["name"] for item in tools_for_phase(
        "execute", approved_form_pending=True)}
    assert approved_names == {"browser_click", "browser_snapshot", "reauthenticate", "ask_user"}
    assert validate_call("browser_fill_fact", {"ref": "e1", "fact_key": "amount"})
    with pytest.raises(ValueError):
        validate_call("browser_fill_fact", {"ref": "e1", "fact_key": "amount",
                                                 "free_text": "48250.00"})


def test_stall_requires_verified_progress():
    detector = StallDetector()
    assert detector.observe("browser_snapshot", {}, progress=False) is None
    assert detector.observe("browser_snapshot", {}, progress=False) is None
    assert detector.observe("browser_snapshot", {}, progress=False) == "reflect"
    detector.observe("browser_snapshot", {}, progress=True)
    assert detector.observe("browser_snapshot", {}, progress=False) is None


def test_prompt_marks_pages_untrusted_and_keeps_last_three():
    observations = [f"Page {index}" for index in range(5)]
    messages = build_messages("Register latest invoice", phase="discover", contract=None,
                              observations=observations, facts=[], plan=[])
    rendered = json.dumps(messages)
    assert "<untrusted_page>Page 4</untrusted_page>" in rendered
    assert "<untrusted_page>Page 2</untrusted_page>" in rendered
    assert "<untrusted_page>Page 0</untrusted_page>" not in rendered
    routed = build_messages("Register latest invoice", phase="discover", contract=None,
                            observations=[], facts=[], plan=[], portal_url="http://p",
                            register_url="http://r")
    assert "http://p/invoices" in json.dumps(routed)
    assert "http://r/invoices/new" in json.dumps(routed)
    assert "contract.sources" in json.dumps(routed)
    assert "free_text" in json.dumps(routed)


def test_locked_goal_tools_offer_distinct_keys_per_source_and_mapping():
    contract = SimpleNamespace(
        sources=[SimpleNamespace(doc_id="doc-a"), SimpleNamespace(doc_id="doc-b")],
        field_map=[SimpleNamespace(target_field="invoice_number",
                                   source_label="Invoice number"),
                   SimpleNamespace(target_field="amount", source_label="Amount")],
    )
    tools = tools_for_phase("execute", contract=contract)
    record = next(item for item in tools if item["function"]["name"] == "record_fact")
    keys = record["function"]["parameters"]["properties"]["key"]["enum"]
    assert keys == ["doc-a.invoice_number", "doc-a.amount",
                    "doc-b.invoice_number", "doc-b.amount"]
    assert "Larkspur" not in json.dumps(tools)


def test_system_guidance_uses_contract_instead_of_example_document():
    from worker.runtime.prompts import SYSTEM

    assert "ls-1042" not in SYSTEM
    assert "Larkspur" not in SYSTEM
    assert "contract.sources" in SYSTEM
    assert "contract.field_map" in SYSTEM


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


def test_locked_tools_guide_navigation_from_missing_fields():
    source = SimpleNamespace(doc_id="doc-a", kind="invoice")
    mapping = SimpleNamespace(target_field="amount", source_label="Amount")
    contract = SimpleNamespace(goal_type=GoalType.register_invoice,
                               sources=[source], field_map=[mapping], filter=None)
    tools = tools_for_phase("execute", contract=contract, facts=[],
                            portal_url="http://p", register_url="http://r")
    navigate = next(item for item in tools if item["function"]["name"] == "browser_navigate")
    urls = navigate["function"]["parameters"]["properties"]["url"]["enum"]
    assert urls == ["http://p/invoices/doc-a"]
    fact = SimpleNamespace(doc_id="doc-a", field_locator="Amount")
    tools = tools_for_phase("execute", contract=contract, facts=[fact],
                            portal_url="http://p", register_url="http://r")
    navigate = next(item for item in tools if item["function"]["name"] == "browser_navigate")
    urls = navigate["function"]["parameters"]["properties"]["url"]["enum"]
    assert "http://r/invoices/new" in urls


def test_export_tool_schema_uses_locked_filter():
    contract = SimpleNamespace(goal_type=GoalType.export_invoices,
                               sources=[], field_map=[],
                               filter={"due_before": "2026-11-01"})
    tools = tools_for_phase("execute", contract=contract)
    write = next(item for item in tools if item["function"]["name"] == "files_write")
    query = write["function"]["parameters"]["properties"]["probe_query"]
    assert query == {"type": "object", "const": {"due_before": "2026-11-01"}}


def test_fill_tool_hides_refs_whose_value_is_already_satisfied():
    contract = SimpleNamespace(goal_type=GoalType.register_invoice,
                               sources=[], field_map=[], filter=None)
    observation = SimpleNamespace(elements=[
        SimpleNamespace(ref="e1", role="combobox", name="Currency", value="INR"),
        SimpleNamespace(ref="e2", role="textbox", name="Source document", value=""),
        SimpleNamespace(ref="e3", role="textbox", name="Amount", value=""),
    ])
    facts = [SimpleNamespace(key="doc.currency", normalized="INR",
                             doc_id="doc", field_locator="Currency"),
             SimpleNamespace(key="doc.amount", normalized="48250.00",
                             doc_id="doc", field_locator="Amount")]
    tools = tools_for_phase("execute", contract=contract, facts=facts,
                            observation=observation)
    fill = next(item for item in tools if item["function"]["name"] == "browser_fill_fact")
    refs = fill["function"]["parameters"]["properties"]["ref"]["enum"]
    assert refs == ["e3"]


def test_trace_is_append_only_and_redacts_secrets(tmp_path):
    writer = TraceWriter(tmp_path, "r1", model="fake", base_url="local",
                         parameters={"max_tokens": 256}, prompt_hash="abc")
    writer.append("tool", {"name": "browser_click", "form_token": "secret"})
    lines = (tmp_path / "r1.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert "secret" not in "\n".join(lines)
    assert json.loads(lines[0])["model"] == "fake"
