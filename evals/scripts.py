"""Deterministic tool-call scripts for the free evaluation tier."""

from __future__ import annotations


def _invoice_steps(case: dict, portal_url: str, register_url: str) -> list[dict]:
    supplier = case["supplier"]
    number = case["invoice_number"]
    script = [
        {"tool": "browser_navigate", "arguments": {
            "url": f"{portal_url}/invoices/{number.lower()}"}},
        {"tool": "browser_snapshot"},
    ]
    script += [{"tool": "record_fact", "arguments": {
        "key": key, "observation_id": "OBS", "field_locator": label, "type": kind,
    }} for key, label, kind in [
        ("number", "Invoice number", "text"), ("amount", "Amount", "amount"),
        ("due", "Due date", "date"), ("currency", "Currency", "text"),
    ]]
    if case["kind"] == "batch":
        proposal = {"goal_type": "register_batch", "supplier": supplier,
                    "selector": "all_unregistered", "max_count": 1}
    else:
        proposal = {"goal_type": "register_invoice", "supplier": supplier,
                    "selector": case.get("selector", "latest")}
        if proposal["selector"] == "invoice_number":
            proposal["invoice_number"] = number
    script.append({"tool": "commit_goal", "arguments": {"contract": proposal}})
    form = [
        {"tool": "browser_navigate", "arguments": {"url": f"{register_url}/invoices/new"}},
        {"tool": "browser_snapshot"},
        {"tool": "browser_select", "target": "Supplier", "arguments": {"option": supplier}},
        {"tool": "browser_snapshot"},
        {"tool": "browser_fill", "target": "Invoice number", "arguments": {"fact_key": "number"}},
        {"tool": "browser_snapshot"},
        {"tool": "browser_fill", "target": "Total" if case.get("fault") == "layout_b" else "Amount",
         "arguments": {"fact_key": "amount"}},
        {"tool": "browser_snapshot"},
        {"tool": "browser_fill", "target": "Payment due" if case.get("fault") == "layout_b" else "Due date",
         "arguments": {"fact_key": "due"}},
        {"tool": "browser_snapshot"},
        {"tool": "browser_fill", "target": "Source document",
         "arguments": {"free_text": number.lower()}},
        {"tool": "browser_snapshot"},
        {"tool": "browser_click", "target": "Record invoice" if case.get("fault") == "layout_b" else "Save"},
    ]
    script += form
    if case.get("fault") == "fail_next_save":
        script += form
    if case.get("decision"):
        script += [{"tool": "browser_snapshot"}, {"tool": "browser_click", "target": "Save"}]
    script += [{"tool": "finish", "arguments": {"summary": "Ready for verification"}}]
    return script


def fake_script(case: dict, portal_url: str, register_url: str) -> list[dict]:
    kind = case["kind"]
    if kind in {"invoice", "batch", "crash"}:
        return _invoice_steps(case, portal_url, register_url)
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
            {"tool": "files_write", "arguments": {"name": case["expected_export"],
                "probe_query": {"due_before": str(case["due_before"])}}},
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
            {"tool": "browser_navigate", "arguments": {"url": f"{portal_url}/invoices"}},
            {"tool": "browser_snapshot"},
            {"tool": "browser_click", "target": "LS-1042"},
            {"tool": "browser_click", "target": "LS-1042"},
            {"tool": "ask_user", "arguments": {"question": "The page changed; should I continue?"}},
        ]
    if kind == "offsite":
        return [
            {"tool": "browser_navigate", "arguments": {"url": "https://example.org/offsite"}},
            {"tool": "ask_user", "arguments": {"question": "The destination was outside the sandbox."}},
        ]
    raise ValueError(f"Unknown fake evaluation kind: {kind}")
