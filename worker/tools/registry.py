"""Bounded model-facing tool schemas and argument validation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

SPECS: dict[str, dict[str, str]] = {
    "browser_navigate": {"url": "string"},
    "browser_click": {"ref": "string"},
    "browser_fill": {"ref": "string", "fact_key": "string?", "user_literal": "string?",
                     "free_text": "string?"},
    "browser_fill_fact": {"ref": "string", "fact_key": "string"},
    "browser_fill_text": {"ref": "string", "free_text": "string"},
    "browser_fill_literal": {"ref": "string", "user_literal": "string"},
    "browser_select": {"ref": "string", "option": "string"},
    "browser_snapshot": {},
    "reauthenticate": {"app": "string"},
    "files_list": {"path": "string"},
    "files_read": {"path": "string"},
    "files_write": {"name": "string", "probe_query": "object"},
    "update_plan": {"steps": "array"},
    "record_fact": {"key": "string", "observation_id": "string",
                    "field_locator": "string", "type": "string"},
    "commit_goal": {"contract": "object"},
    "revise_goal": {"contract": "object"},
    "ask_user": {"question": "string"},
    "unsupported": {"reason": "string"},
    "finish": {"summary": "string"},
}

DESCRIPTIONS = {
    "browser_navigate": "Open an allowed full URL. Navigate to the relevant source or destination; do not reopen the same page repeatedly.",
    "browser_snapshot": "Read the current page and get an observation_id, document fields, and current element refs.",
    "browser_click": "Click a ref from the latest observation. Submitting a form passes through policy and approval gates.",
    "browser_fill": "Fill a current form ref from exactly one recorded fact, user literal, or permitted free-text value.",
    "browser_fill_fact": "Fill a mapped form field from a previously recorded fact key for the same frozen source.",
    "browser_fill_text": "Fill a non-obligation form field with permitted text, such as the current source document ID.",
    "browser_fill_literal": "Fill one field from a value explicitly written by the user in the request.",
    "browser_select": "Choose an exact visible option in a current select ref.",
    "record_fact": "Copy one field from the current source detail document. Use an exact documents[].fields label; type is text, amount, or date. Keep a distinct key for each source and field.",
    "commit_goal": "Lock a code-resolved goal that matches the user's action and constraints. Supported goal types are in the schema.",
    "finish": "Request independent code verification after the work is done; this does not declare success.",
    "unsupported": "End a request outside the supported goal types with a plain-language reason.",
}

GOAL_SCHEMA = {
    "type": "object",
    "properties": {
        "goal_type": {"type": "string", "enum": [
            "register_invoice", "check_or_register_invoice", "register_batch",
            "update_supplier_contact", "export_invoices",
        ]},
        "supplier": {"type": "string"},
        "selector": {"type": "string", "enum": [
            "latest", "invoice_number", "all_unregistered", "message", "filter",
        ]},
        "invoice_number": {"type": "string"},
        "source_doc_id": {"type": "string"},
        "max_count": {"type": "integer"},
        "due_before": {"type": "string", "format": "date"},
        "extra_criteria": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["goal_type"],
    "additionalProperties": False,
}


def _schema(spec: dict[str, str]) -> dict:
    properties = {key: {"type": kind.removesuffix("?")} for key, kind in spec.items()}
    if "field_locator" in spec:
        properties["type"]["enum"] = ["text", "amount", "date"]
    if "contract" in spec:
        properties["contract"] = GOAL_SCHEMA
    return {"type": "object", "properties": properties,
            "required": [key for key, kind in spec.items() if not kind.endswith("?")],
            "additionalProperties": False}


TOOLS = [{"type": "function", "function": {"name": name,
                                          "description": DESCRIPTIONS.get(name, name.replace("_", " ")),
                                          "parameters": _schema(spec)}}
         for name, spec in SPECS.items()]


def tools_for_phase(phase: str, *, allow_revision: bool = False,
                    ready_to_verify: bool = False,
                    approved_form_pending: bool = False,
                    contract=None, facts: list | None = None,
                    portal_url: str | None = None,
                    register_url: str | None = None,
                    observation=None) -> list[dict]:
    if ready_to_verify:
        return [tool for tool in TOOLS if tool["function"]["name"] == "finish"]
    if approved_form_pending:
        allowed = {"browser_click", "browser_snapshot", "reauthenticate", "ask_user"}
        return [tool for tool in TOOLS if tool["function"]["name"] in allowed]
    if phase == "discover":
        excluded = {"revise_goal", "files_write", "browser_fill"}
    else:
        excluded = {"commit_goal", "browser_fill"}
        if not allow_revision:
            excluded.add("revise_goal")
    selected = [deepcopy(tool) for tool in TOOLS
                if tool["function"]["name"] not in excluded]
    if contract:
        keys = [f"{source.doc_id}.{mapping.target_field}"
                for source in contract.sources for mapping in contract.field_map]
        recorded = {(fact.doc_id, fact.field_locator) for fact in facts or []}
        missing = [source for source in contract.sources if any(
            (source.doc_id, mapping.source_label) not in recorded
            for mapping in contract.field_map
        )]
        urls = []
        if portal_url:
            urls = [f"{portal_url}/{'messages' if source.kind == 'message' else 'invoices'}"
                    f"/{source.doc_id}" for source in missing]
        if register_url and contract.sources and len(missing) < len(contract.sources):
            if contract.goal_type == "update_supplier_contact":
                urls.append(f"{register_url}/suppliers/{contract.supplier_id}/edit")
            else:
                urls.append(f"{register_url}/invoices/new")
        for tool in selected:
            name = tool["function"]["name"]
            properties = tool["function"]["parameters"]["properties"]
            if name == "record_fact" and keys:
                properties["key"]["enum"] = keys
            elif name == "browser_navigate" and urls:
                properties["url"]["enum"] = urls
            elif name == "files_write" and getattr(contract, "filter", None) is not None:
                properties["probe_query"]["const"] = contract.filter
            elif name in {"browser_fill_fact", "browser_fill_text"} and observation:
                if name == "browser_fill_fact":
                    values = {fact.normalized for fact in facts or []}
                    refs = [element.ref for element in observation.elements
                            if element.role in {"textbox", "date", "textarea"}
                            and element.name.casefold() != "source document"
                            and element.value not in values]
                else:
                    refs = [element.ref for element in observation.elements
                            if element.role in {"textbox", "date", "textarea"}
                            and not element.value]
                properties["ref"]["enum"] = refs
        selected = [tool for tool in selected if not (
            tool["function"]["name"] in {"browser_fill_fact", "browser_fill_text"}
            and tool["function"]["parameters"]["properties"]["ref"].get("enum") == []
        )]
    return selected


def validate_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name not in SPECS:
        raise ValueError("Unknown tool")
    spec = SPECS[name]
    if set(arguments) - set(spec):
        raise ValueError("Unexpected tool argument")
    if any(key not in arguments for key, kind in spec.items() if not kind.endswith("?")):
        raise ValueError("Missing tool argument")
    for key, value in arguments.items():
        kind = spec[key].removesuffix("?")
        expected = {"string": str, "object": dict, "array": list}[kind]
        if not isinstance(value, expected):
            raise TypeError(f"Invalid {key}")
    if name == "browser_fill" and sum(key in arguments for key in
                                      ("fact_key", "user_literal", "free_text")) != 1:
        raise ValueError("Choose exactly one fill source")
    return arguments
