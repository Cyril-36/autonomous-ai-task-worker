"""Resolve proposed goals through read-only probes before enabling writes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from uuid import uuid4

from worker.contracts import (
    Criterion,
    FactType,
    FieldMapping,
    GoalContract,
    GoalProposal,
    GoalType,
    Obligation,
    RequestConstraints,
    SourceRef,
)

INVOICE_FIELDS = [
    FieldMapping(target_field="invoice_number", source_label="Invoice number", type=FactType.text),
    FieldMapping(target_field="amount", source_label="Amount", type=FactType.amount),
    FieldMapping(target_field="currency", source_label="Currency", type=FactType.text),
    FieldMapping(target_field="due_date", source_label="Due date", type=FactType.date),
]
CONTACT_FIELDS = [
    FieldMapping(target_field="contact_name", source_label="Contact name", type=FactType.text),
    FieldMapping(target_field="contact_email", source_label="Contact email", type=FactType.text),
    FieldMapping(target_field="remittance_email", source_label="Remittance email", type=FactType.text),
]


@dataclass(frozen=True)
class GoalRejection:
    code: str
    reason: str
    candidates: list[str] = field(default_factory=list)


def _source(row: dict, kind: str = "invoice") -> SourceRef:
    return SourceRef(
        kind=kind, doc_id=row["doc_id"], revision=str(row["revision"]),
        supplier_id=row["supplier_id"],
        key=row["invoice_number"] if kind == "invoice" else row["doc_id"],
    )


def _obligation(kind: str, description: str, params: dict | None = None) -> Obligation:
    return Obligation(obligation_id=kind, kind=kind, description=description, params=params or {})


def _supplier_candidates(text: str, suppliers: list[dict]) -> list[dict]:
    query = text.strip().casefold()
    return [row for row in suppliers if query == row["name"].casefold() or query in {
        alias.strip().casefold() for alias in row.get("aliases", "").split(",") if alias.strip()
    }]


def _valid_extra(criterion: Criterion) -> bool:
    return (
        criterion.probe == "register_invoice"
        and set(criterion.where) == {"supplier_id", "invoice_number"}
        and bool(criterion.expect)
        and set(criterion.expect) <= {
            "supplier_id", "invoice_number", "amount", "currency", "due_date",
        }
    )


async def commit_goal(
    proposal: GoalProposal | dict, request_text: str, probes, *, run_id: str,
) -> GoalContract | GoalRejection:
    if isinstance(proposal, dict):
        try:
            proposal = GoalProposal.model_validate(proposal)
        except ValueError:
            return GoalRejection("unsupported", "Request does not fit a supported goal type")
    request = request_text.casefold()
    suppliers = await probes.register_suppliers()
    supplier = None
    if proposal.supplier:
        candidates = _supplier_candidates(proposal.supplier, suppliers)
        if len(candidates) != 1:
            return GoalRejection("needs_clarification", "Supplier name is ambiguous",
                                 [row["name"] for row in candidates])
        supplier = candidates[0]
        exact_in_request = supplier["name"].casefold() in request
        unique_alias_in_request = any(
            alias.strip().casefold() in request and
            len(_supplier_candidates(alias.strip(), suppliers)) == 1
            for alias in supplier.get("aliases", "").split(",") if alias.strip()
        )
        if not exact_in_request and not unique_alias_in_request:
            return GoalRejection("request_mismatch", "Supplier is not unambiguously named in request")
    elif proposal.goal_type != GoalType.export_invoices:
        return GoalRejection("needs_clarification", "Name a supplier")

    latest_requested = bool(re.search(r"\b(latest|newest|most recent)\b", request))
    required_selectors = {
        GoalType.check_or_register_invoice: "invoice_number",
        GoalType.register_batch: "all_unregistered",
        GoalType.update_supplier_contact: "message",
        GoalType.export_invoices: "filter",
    }
    required = required_selectors.get(proposal.goal_type)
    if required and proposal.selector not in {None, required}:
        return GoalRejection("request_mismatch", f"This goal requires the {required} selector")
    if latest_requested and proposal.selector not in {"latest", None}:
        return GoalRejection("request_mismatch", "Latest request cannot select a fixed number")
    if proposal.selector == "invoice_number" and (
        not proposal.invoice_number or proposal.invoice_number.casefold() not in request
    ):
        return GoalRejection("request_mismatch", "Invoice number must appear in request")

    constraints = RequestConstraints(
        supplier_text=proposal.supplier, selector=proposal.selector,
        invoice_numbers=[proposal.invoice_number] if proposal.invoice_number else [],
        dates=[proposal.due_before] if proposal.due_before else [], cap=proposal.max_count,
    )
    sources: list[SourceRef] = []
    remaining: list[SourceRef] = []
    field_map: list[FieldMapping] = []
    obligations: list[Obligation] = []
    frozen_filter = None
    supplier_id = supplier["id"] if supplier else None
    if supplier:
        obligations.append(_obligation("supplier_resolved", "Supplier resolves to exactly one record"))

    if proposal.goal_type in {GoalType.register_invoice, GoalType.check_or_register_invoice}:
        if proposal.goal_type == GoalType.check_or_register_invoice and not proposal.invoice_number:
            return GoalRejection("request_mismatch", "Check requires an invoice number")
        portal = await probes.portal_invoices(supplier_id)
        if proposal.selector == "latest" or (latest_requested and not proposal.invoice_number):
            if not portal:
                return GoalRejection("blocked", "No portal invoices for supplier")
            newest_date = max(row["issue_date"] for row in portal)
            matches = [row for row in portal if row["issue_date"] == newest_date]
            if len(matches) != 1:
                return GoalRejection("needs_clarification", "Latest issue date is tied",
                                     [row["invoice_number"] for row in matches])
            chosen = matches[0]
            constraints = constraints.model_copy(update={"selector": "latest"})
            obligations.append(_obligation("source_is_latest", "Source is latest by issue date"))
        elif proposal.invoice_number:
            matches = [row for row in portal if row["invoice_number"] == proposal.invoice_number]
            if not matches:
                return GoalRejection("blocked", "Invoice not found on the portal")
            if len(matches) != 1:
                return GoalRejection("needs_clarification", "Invoice number matches multiple documents",
                                     [row["doc_id"] for row in matches])
            chosen = matches[0]
            constraints = constraints.model_copy(update={"selector": "invoice_number"})
        else:
            return GoalRejection("request_mismatch", "Select latest or an invoice number")
        if proposal.source_doc_id and proposal.source_doc_id != chosen["doc_id"]:
            return GoalRejection("source_mismatch", "Proposed source differs from code-resolved source")
        sources = [_source(chosen)]
        field_map = INVOICE_FIELDS
        prior = [row for row in await probes.register_invoices(supplier_id=supplier_id)
                 if row["invoice_number"] == chosen["invoice_number"]]
        obligations.extend([
            _obligation("record_count", "Exactly one saved invoice for supplier and number"),
            _obligation("record_fields", "Saved fields match the frozen source"),
        ])
        if proposal.goal_type == GoalType.check_or_register_invoice and prior:
            obligations.append(_obligation("no_write", "Existing record remains unchanged",
                                           {"record_id": str(prior[0].get("id", "")),
                                            "version": str(prior[0].get("version", ""))}))

    elif proposal.goal_type == GoalType.register_batch:
        cap = proposal.max_count
        if not cap or cap < 1 or cap > 10 or not re.search(rf"\b{cap}\b", request):
            return GoalRejection("request_mismatch", "Explicit batch cap must appear in request")
        portal = await probes.portal_invoices(supplier_id)
        registered = await probes.register_invoices(supplier_id=supplier_id)
        existing = {row["invoice_number"] for row in registered}
        eligible = sorted((row for row in portal if row["invoice_number"] not in existing),
                          key=lambda row: (row["issue_date"], row["invoice_number"]))
        sources = [_source(row) for row in eligible[:cap]]
        remaining = [_source(row) for row in eligible[cap:]]
        field_map = INVOICE_FIELDS
        obligations.extend([
            _obligation("record_count", "Each selected invoice is saved exactly once"),
            _obligation("record_fields", "Each selected record matches its source"),
            _obligation("batch_complete", "All eligible invoices fit the batch cap"),
        ])

    elif proposal.goal_type == GoalType.update_supplier_contact:
        if not proposal.source_doc_id:
            return GoalRejection("request_mismatch", "Contact update needs a source message")
        try:
            message = await probes.portal_document(proposal.source_doc_id)
        except (LookupError, KeyError):
            return GoalRejection("blocked", "Source message not found")
        if message["supplier_id"] != supplier_id or "contact_name" not in message:
            return GoalRejection("source_mismatch", "Message does not belong to supplier")
        sources = [_source(message, "message")]
        field_map = CONTACT_FIELDS
        obligations.append(_obligation("contact_fields", "Supplier contact matches source message"))
        current = await probes.register_supplier(supplier_id)
        if current.get("remittance_email") != message["remittance_email"]:
            obligations.append(_obligation("approval_recorded", "Remittance change was approved"))

    elif proposal.goal_type == GoalType.export_invoices:
        due = proposal.due_before
        if not due or not isinstance(due, date):
            return GoalRejection("request_mismatch", "Explicit due-before date required")
        if due.isoformat() not in request and due.strftime("%d %b %Y").casefold() not in request:
            return GoalRejection("request_mismatch", "Export date is not in request")
        frozen_filter = {"due_before": due.isoformat()}
        if supplier_id:
            frozen_filter["supplier_id"] = supplier_id
        obligations.append(_obligation("export_rows", "Export rows exactly match register filter"))

    else:
        return GoalRejection("unsupported", "Request does not fit a supported goal type")

    source_values = {}
    for ref in sources:
        try:
            document = await probes.portal_document(ref.doc_id)
        except (LookupError, KeyError):
            return GoalRejection("source_mismatch", "Source changed during goal commitment")
        if (str(document.get("revision")) != ref.revision
                or document.get("supplier_id") != ref.supplier_id):
            return GoalRejection("source_mismatch", "Source changed during goal commitment")
        if ref.kind == "invoice" and document.get("invoice_number") != ref.key:
            return GoalRejection("source_mismatch", "Invoice number changed during commitment")
        values = {}
        for mapping in field_map:
            key = mapping.source_label.casefold().replace(" ", "_")
            if key not in document or document[key] in {None, ""}:
                return GoalRejection("needs_clarification", f"Source lacks {mapping.source_label}")
            values[mapping.source_label] = str(document[key])
        source_values[ref.doc_id] = values
    obligations = [
        item.model_copy(update={"params": {**item.params, "source_values": source_values}})
        if item.kind in {"record_fields", "contact_fields"} else item
        for item in obligations
    ]

    for index, criterion in enumerate(proposal.extra_criteria, 1):
        if not _valid_extra(criterion):
            return GoalRejection("unsupported", "Extra criterion uses an unregistered probe")
        obligations.append(_obligation("extra", f"Extra criterion {index}", criterion.model_dump()))
    return GoalContract(
        contract_id=uuid4().hex, run_id=run_id, goal_type=proposal.goal_type,
        constraints=constraints, supplier_id=supplier_id,
        supplier_name=supplier["name"] if supplier else None, sources=sources,
        batch_remaining=remaining, filter=frozen_filter, field_map=field_map,
        obligations=obligations, locked_at=datetime.now(UTC),
    )


def revise_goal(contract: GoalContract, proposal: GoalProposal, *,
                wrote_business_data: bool, confirmed: bool = False) -> GoalContract | GoalRejection:
    if wrote_business_data:
        return GoalRejection("locked_after_write", "Goal cannot change after a business write")
    if not all(_valid_extra(criterion) for criterion in proposal.extra_criteria):
        return GoalRejection("unsupported", "Extra criterion uses an unregistered probe")
    changed = (
        proposal.goal_type != contract.goal_type or proposal.supplier != contract.constraints.supplier_text
        or proposal.selector != contract.constraints.selector
        or ([proposal.invoice_number] if proposal.invoice_number else []) !=
        contract.constraints.invoice_numbers or proposal.max_count != contract.constraints.cap
        or ([proposal.due_before] if proposal.due_before else []) != contract.constraints.dates
    )
    if changed and not confirmed:
        return GoalRejection("confirmation_required", "Material goal change needs user confirmation")
    if changed:
        return GoalRejection("recommit_required", "Resolve changed sources through commit_goal")
    extras = [_obligation("extra", f"Extra criterion {index}", criterion.model_dump())
              for index, criterion in enumerate(proposal.extra_criteria, 1)]
    fixed = [obligation for obligation in contract.obligations if obligation.kind != "extra"]
    return contract.model_copy(update={"obligations": fixed + extras,
                                       "revision": contract.revision + 1})
