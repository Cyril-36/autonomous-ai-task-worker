"""Deterministic tool-call scripts for the free evaluation tier."""

from __future__ import annotations

SCRIPTED_KINDS = {"invoice", "batch", "crash", "existing", "export", "ambiguity",
                  "missing_source", "unsupported", "provider_failure", "stale_ref", "offsite"}


def _invoice_steps(case: dict) -> list[dict]:
    supplier = case["supplier"]
    number = case["invoice_number"]
    doc = number.lower()
    if case["kind"] == "batch":
        proposal = {"goal_type": "register_batch", "supplier": supplier,
                    "selector": "all_unregistered", "max_count": 1}
    else:
        proposal = {"goal_type": "register_invoice", "supplier": supplier,
                    "selector": case.get("selector", "latest")}
        if proposal["selector"] == "invoice_number":
            proposal["invoice_number"] = number
    layout_b = case.get("fault") == "layout_b"
    form = [
        {"tool": "open_page", "arguments": {"app": "register", "page": "new_invoice"}},
        {"tool": "fill_form", "arguments": {"fields": [
            {"label": "Supplier", "fact": "goal.supplier"},
            {"label": "Invoice number", "fact": f"{doc}.invoice_number"},
            {"label": "Total" if layout_b else "Amount", "fact": f"{doc}.amount"},
            {"label": "Payment due" if layout_b else "Due date", "fact": f"{doc}.due_date"},
            {"label": "Currency", "fact": f"{doc}.currency"},
            {"label": "Source document", "fact": f"{doc}.document_id"},
        ]}},
        {"tool": "submit_form"},
    ]
    script = [
        {"tool": "commit_goal", "arguments": {"contract": proposal}},
        {"tool": "open_page", "arguments": {"app": "portal", "page": "invoice", "id": doc}},
        {"tool": "record_facts", "arguments": {
            "labels": ["Invoice number", "Amount", "Due date", "Currency"]}},
        *form,
    ]
    if case.get("fault") == "fail_next_save":
        script += form
    if case.get("decision"):
        script += [{"tool": "submit_form"}]
    script += [{"tool": "finish", "arguments": {"summary": "Ready for verification"}}]
    return script


def fake_script(case: dict) -> list[dict]:
    kind = case["kind"]
    if kind in {"invoice", "batch", "crash"}:
        return _invoice_steps(case)
    if kind == "existing":
        return [
            {"tool": "commit_goal", "arguments": {"contract": {
                "goal_type": "check_or_register_invoice", "supplier": case["supplier"],
                "selector": "invoice_number", "invoice_number": case["invoice_number"]}}},
            {"tool": "finish", "arguments": {"summary": "Ready for verification"}},
        ]
    if kind == "export":
        return [
            {"tool": "commit_goal", "arguments": {"contract": {
                "goal_type": "export_invoices", "selector": "filter",
                "due_before": str(case["due_before"])}}},
            {"tool": "files_write", "arguments": {"name": "due.csv"}},
            {"tool": "finish", "arguments": {"summary": "Ready for verification"}},
        ]
    if kind == "ambiguity":
        return [{"tool": "commit_goal", "arguments": {"contract": {
            "goal_type": "register_invoice", "supplier": "Larkspur", "selector": "latest"}}}]
    if kind == "missing_source":
        return [
            {"tool": "commit_goal", "arguments": {"contract": {
                "goal_type": "register_invoice", "supplier": "Larkspur Supplies",
                "selector": "latest", "source_doc_id": "incorrect-source"}}},
            {"tool": "ask_user", "arguments": {"question": "The selected source does not match. Which invoice?"}},
        ]
    if kind == "unsupported":
        return [{"tool": "commit_goal", "arguments": {"contract": {
            "goal_type": "make_payment"}}}]
    if kind == "provider_failure":
        return [{"error": "timeout"}]
    if kind == "stale_ref":
        return [
            {"tool": "open_page", "arguments": {"app": "portal", "page": "invoices"}},
            {"tool": "browser_click", "target": "LS-1042"},
            {"tool": "browser_click", "arguments": {"ref": "e999"}},
            {"tool": "ask_user", "arguments": {"question": "The page changed; should I continue?"}},
        ]
    if kind == "offsite":
        return [
            {"tool": "open_page", "arguments": {"app": "elsewhere", "page": "home"}},
            {"tool": "ask_user", "arguments": {"question": "The destination was outside the sandbox."}},
        ]
    raise ValueError(f"Unknown fake evaluation kind: {kind}")
