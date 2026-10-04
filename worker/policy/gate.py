"""Check every business write before a network allowance is armed."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from worker.contracts import FileWriteIntent, GateDecision, GoalType, MutationIntent
from worker.policy.approvals import validate_approval
from worker.policy.normalize import normalize
from worker.policy.provenance import check_fill
from worker.tools.files import FILENAME


def _deny(code: str, reason: str) -> GateDecision:
    return GateDecision(allowed=False, code=code, reason=reason)


def _base(state, run_id: str) -> GateDecision | None:
    if state.phase != "execute":
        return _deny("phase_discover", "Writes are allowed only after goal commitment")
    if state.contract is None or state.contract.run_id != run_id:
        return _deny("no_contract", "No locked goal contract for this run")
    return None


def check_mutation(state, intent: MutationIntent) -> GateDecision:
    if base := _base(state, intent.run_id):
        return base
    parsed = urlsplit(intent.action_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in state.allowed_origins or origin != intent.origin:
        return _deny("origin_blocked", "Target origin is outside the sandbox")
    if parsed.path.startswith("/api/"):
        return _deny("path_blocked", "Browser cannot write to probe APIs")
    goal = state.contract.goal_type
    allowed_path = (
        bool(re.fullmatch(r"/invoices(?:/\d+)?", parsed.path)) if goal in {
            GoalType.register_invoice, GoalType.check_or_register_invoice, GoalType.register_batch,
            GoalType.sync_existing_invoice,
        } else bool(re.fullmatch(r"/suppliers/[a-z0-9-]+", parsed.path))
        if goal == GoalType.update_supplier_contact else False
    )
    if not allowed_path:
        return _deny("path_blocked", "Write path does not match the locked goal")
    if goal == GoalType.sync_existing_invoice:
        target = next((item for item in state.contract.obligations
                       if item.kind == "target_record"), None)
        if (target is None or parsed.path != f"/invoices/{target.params['record_id']}"
                or str(intent.target_version) != target.params["version"]):
            return _deny("path_blocked", "Correction must update the frozen existing record")
    if not intent.form_token or intent.fields.get("form_token") != intent.form_token:
        return _deny("not_a_mutation", "A current form token is required")
    if any(p.state == "dispatching" and p.target_key == intent.target_key for p in state.pending):
        return _deny("pending_unresolved", "Previous write to this target is unresolved")
    source = intent.source
    if not source or source not in state.contract.sources:
        return _deny("source_mismatch", "Write source is not in the frozen contract")
    if intent.fields.get("source_doc_id", source.doc_id) != source.doc_id:
        return _deny("source_mismatch", "Form source document differs from frozen source")
    if intent.fields.get("supplier_id", source.supplier_id) != source.supplier_id:
        return _deny("source_mismatch", "Form supplier differs from frozen source")
    if intent.fields.get("invoice_number", source.key) != source.key and source.kind == "invoice":
        return _deny("source_mismatch", "Form invoice number differs from frozen source")
    frozen = state.source_values.get(source.doc_id)
    if not frozen:
        return _deny("source_mismatch", "Frozen source fields are missing")
    for mapping in state.contract.field_map:
        target = mapping.target_field
        fill_source = intent.filled_from.get(target)
        if not fill_source or target not in intent.fields:
            return _deny("provenance_failed", f"No provenance for {target}")
        field_value = intent.fields[target]
        if not check_fill(state, fill_source.kind, field_value, fill_source.fact_key,
                          mapping.type, obligation_checked=True):
            return _deny("provenance_failed", f"Fill source is not valid for {target}")
        if fill_source.kind == "fact":
            fact = state.facts.get(fill_source.fact_key)
            if fact.doc_id != source.doc_id or fact.revision != source.revision:
                return _deny("source_mismatch", f"Fact for {target} belongs to another document")
        try:
            actual = normalize(field_value, mapping.type)
            expected = normalize(frozen[mapping.source_label], mapping.type)
        except (KeyError, ValueError):
            return _deny("field_mismatch", f"Cannot compare {target} to frozen source")
        if actual != expected:
            return _deny("field_mismatch", f"{target} differs from the frozen source")
    threshold = Decimal(str(state.policy.get("threshold", "100000.00")))
    amount = Decimal(intent.fields.get("amount", "0"))
    requires_approval = (amount >= threshold or intent.target_version is not None
                         or state.contract.goal_type == GoalType.update_supplier_contact
                         and "remittance_email" in intent.fields)
    if requires_approval:
        approvals = [approval for approval in state.approvals if approval.run_id == intent.run_id]
        if not approvals:
            return _deny("needs_approval", "Company policy requires approval for this write")
        if not any(validate_approval(approval, intent, int(state.policy["version"]))
                   for approval in approvals):
            return _deny("approval_invalid", "Approval expired or no longer matches this write")
    return GateDecision(allowed=True, code="allowed", reason="Write matches locked contract")


def check_file_write(state, intent: FileWriteIntent) -> GateDecision:
    if base := _base(state, intent.run_id):
        return base
    if state.contract.goal_type != GoalType.export_invoices:
        return _deny("path_blocked", "This goal does not permit export")
    path = PurePosixPath(intent.path)
    if path.parent != PurePosixPath("exports") or not FILENAME.fullmatch(path.name):
        return _deny("filename_invalid", "Export must use a safe CSV filename under exports")
    if intent.probe_query != state.contract.filter:
        return _deny("query_mismatch", "Export query differs from the locked filter")
    if any(p.state == "dispatching" for p in state.pending):
        return _deny("pending_unresolved", "Resolve the business write before exporting")
    return GateDecision(allowed=True, code="allowed", reason="Export matches locked filter")
