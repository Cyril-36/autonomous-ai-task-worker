"""Bounded model-facing tool schemas and argument validation."""

from __future__ import annotations

from typing import Any

SPECS: dict[str, dict[str, str]] = {
    "browser_navigate": {"url": "string"},
    "browser_click": {"ref": "string"},
    "browser_fill": {"ref": "string", "fact_key": "string?", "user_literal": "string?",
                     "free_text": "string?"},
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
    "finish": {"summary": "string"},
}


def _schema(spec: dict[str, str]) -> dict:
    properties = {key: {"type": kind.removesuffix("?")} for key, kind in spec.items()}
    return {"type": "object", "properties": properties,
            "required": [key for key, kind in spec.items() if not kind.endswith("?")],
            "additionalProperties": False}


TOOLS = [{"type": "function", "function": {"name": name, "description": name.replace("_", " "),
                                          "parameters": _schema(spec)}}
         for name, spec in SPECS.items()]


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
