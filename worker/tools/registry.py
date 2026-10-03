"""Bounded model-facing tool schemas and argument validation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

SPECS: dict[str, dict[str, str]] = {
    # Offered to the model
    "open_page": {"app": "string", "page": "string", "id": "string?"},
    "browser_click": {"ref": "string"},
    "browser_snapshot": {},
    "record_facts": {"labels": "array", "observation_id": "string?"},
    "fill_form": {"fields": "array"},
    "submit_form": {},
    "files_list": {"path": "string"},
    "files_read": {"path": "string"},
    "files_write": {"name": "string", "probe_query": "object?"},
    "update_plan": {"steps": "array"},
    "commit_goal": {"contract": "object"},
    "revise_goal": {"contract": "object"},
    "ask_user": {"question": "string"},
    "unsupported": {"reason": "string"},
    "finish": {"summary": "string"},
    # Low-level tools kept for scripted tests and recovery; not offered to the model
    "browser_navigate": {"url": "string"},
    "browser_fill": {"ref": "string", "fact_key": "string?", "user_literal": "string?",
                     "free_text": "string?"},
    "browser_fill_fact": {"ref": "string", "fact_key": "string"},
    "browser_fill_text": {"ref": "string", "free_text": "string"},
    "browser_fill_literal": {"ref": "string", "user_literal": "string"},
    "browser_select": {"ref": "string", "option": "string"},
    "record_fact": {"key": "string", "observation_id": "string",
                    "field_locator": "string", "type": "string"},
    "reauthenticate": {"app": "string"},
}

DESCRIPTIONS = {
    "open_page": "Open a named page of a company app, e.g. app=portal page=invoice id=<document id>. "
                 "Pages are listed in the company context. Returns a fresh observation.",
    "browser_click": "Click an element ref from the latest observation (links, filters, buttons). "
                     "Use submit_form to submit a form.",
    "browser_snapshot": "Re-read the current page.",
    "record_facts": "Copy labelled values from a document on the current page into your facts. "
                    "Give the exact field labels shown in the observation's documents. "
                    "Code copies the values and names each fact <document id>.<label>.",
    "fill_form": "Fill fields of the form on the current page in one call. Each item: "
                 "{label: visible field label, fact: fact key} or {label, text: plain text} for "
                 "free-text fields only. Code finds each field by its label and checks every value.",
    "submit_form": "Submit the form on the current page. Policy, approval and duplicate checks run "
                   "first; the result says whether the save was confirmed.",
    "files_list": "List files under the workspace.",
    "files_read": "Read a workspace file.",
    "files_write": "Write the export for the locked goal to exports/<name>.csv. "
                   "Rows come from the system of record using the goal's filter.",
    "update_plan": "Write or revise your short plan as a list of step strings.",
    "commit_goal": "Lock the goal once you understand the request. Code checks it against the "
                   "request, resolves the source documents and derives the checks that must pass.",
    "revise_goal": "Change the locked goal after a failed verification. Changes to supplier, "
                   "documents, numbers or filters need the user's confirmation.",
    "ask_user": "Ask the user one clear question when the request or evidence is ambiguous.",
    "unsupported": "End the run when the action the user asked for is not one of the supported "
                   "goal types, with a plain-language reason.",
    "finish": "Request independent verification once the work is done. Does not declare success.",
}

FIELD_ITEM = {
    "type": "object",
    "properties": {"label": {"type": "string"}, "fact": {"type": "string"},
                   "text": {"type": "string"}},
    "required": ["label"],
    "additionalProperties": False,
}

GOAL_SCHEMA = {
    "type": "object",
    "properties": {
        "requested_action": {"type": "string", "description":
                             "The action the user asked for, restated in a few words, "
                             "before choosing goal_type"},
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
    "required": ["requested_action", "goal_type"],
    "additionalProperties": False,
}


def _schema(spec: dict[str, str]) -> dict:
    properties = {key: {"type": kind.removesuffix("?")} for key, kind in spec.items()}
    if "field_locator" in spec:
        properties["type"]["enum"] = ["text", "amount", "date"]
    if "contract" in spec:
        properties["contract"] = GOAL_SCHEMA
    if "labels" in spec:
        properties["labels"]["items"] = {"type": "string"}
    if "fields" in spec:
        properties["fields"]["items"] = FIELD_ITEM
    if "steps" in spec:
        properties["steps"]["items"] = {"type": "string"}
    return {"type": "object", "properties": properties,
            "required": [key for key, kind in spec.items() if not kind.endswith("?")],
            "additionalProperties": False}


TOOLS = [{"type": "function", "function": {"name": name,
                                          "description": DESCRIPTIONS.get(name, name.replace("_", " ")),
                                          "parameters": _schema(spec)}}
         for name, spec in SPECS.items()]

COMMON = {"open_page", "browser_click", "browser_snapshot", "record_facts", "ask_user",
          "update_plan", "files_list", "files_read"}
DISCOVER = COMMON | {"commit_goal", "unsupported"}
EXECUTE = COMMON | {"fill_form", "submit_form", "files_write", "finish"}
APPROVED_FORM = {"submit_form", "browser_snapshot", "ask_user"}


def tools_for_phase(phase: str, *, allow_revision: bool = False,
                    ready_to_verify: bool = False,
                    approved_form_pending: bool = False, **_ignored) -> list[dict]:
    """The same goal-agnostic tool set for every task; only the phase changes it."""
    if ready_to_verify:
        names = {"finish"}
    elif approved_form_pending:
        names = APPROVED_FORM
    elif phase == "discover":
        names = DISCOVER
    else:
        names = EXECUTE | ({"revise_goal"} if allow_revision else set())
    return [deepcopy(tool) for tool in TOOLS if tool["function"]["name"] in names]


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
