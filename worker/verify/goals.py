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


NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10}
DATE_FORMATS = ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y", "%d/%m/%Y",
                "%d-%m-%Y")
DATE_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}"                                   # 2026-11-01
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?[a-z]+\s+\d{4}"   # 1 November 2026, 15th of Nov 2026
    r"|[a-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"           # November 1, 2026
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{4}")                         # 15/11/2026, day first


# Does the user's own request ask for the action a goal type carries out?
#
# Three answers: "clear" (an action of this goal on this goal's kind of object, not negated),
# "none" (no such action, or only negated ones) and "unclear" (the action word is there but aimed
# at something else, or the request only asks to check). Code refuses "none" and asks the user to
# confirm "unclear", so a request for something else (a refund, a payment, a deletion) cannot
# become a write. It is a lexical check with known limits, which is why its doubt goes to a person.
_TOKEN = re.compile(r"[A-Za-z]{2}-\d+|[A-Za-z]+(?:'[a-z]+)?|\d+|[.;:!?]")
_NEGATION = {"not", "don't", "dont", "doesn't", "never", "without", "avoid", "stop", "no",
             "haven't", "hasn't", "didn't", "isn't", "aren't", "shouldn't", "won't"}
_FILLER = {"a", "an", "the", "their", "its", "our", "your", "this", "that", "these", "those",
           "any", "all", "every", "each", "up", "to", "of", "latest", "newest", "most",
           "recent", "last", "new", "unregistered", "missing", "outstanding", "next", "first",
           "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
           "please", "back"}
_DETERMINERS = {"a", "an", "the", "their", "its", "our", "your", "this", "that", "on", "from"}
_INVOICE_OBJECT = re.compile(r"^(?:invoices?|bills?|it|them|[a-z]{2}-\d+)$")
_RECORD_VERB = re.compile(r"^(?:register|enter|record|log|add|put|file|book|input|capture|"
                          r"insert)(?:s|ed|ing)?$")
_PASSIVE_REGISTER = re.compile(r"\b(?:need|needs|has|have) to go$|\b(?:must|should) go$")
_INVOICE_NUMBER = re.compile(r"\b[a-z]{2,10}-\d+\b", re.IGNORECASE)
_OTHER_OBJECT = re.compile(r"\b(?:refund|credit note|payment|void|cancel|cancellation)\b")
_ACTION_WORD = re.compile(r"^(?:register|enter|record|log|add|put|file|book|input|capture|"
                          r"insert|export|download|update|change|replace|correct|sync)\w*$")
_GOAL_RULES: dict[GoalType, dict] = {
    GoalType.register_invoice: {"verb": _RECORD_VERB, "object": _INVOICE_OBJECT},
    GoalType.register_batch: {"verb": _RECORD_VERB, "object": _INVOICE_OBJECT},
    # it writes when the invoice is missing, so a check alone is not enough
    GoalType.check_or_register_invoice: {"verb": _RECORD_VERB, "object": _INVOICE_OBJECT,
                                         "unclear": re.compile(r"^(?:already|check|have)$")},
    GoalType.update_supplier_contact: {
        "verb": re.compile(r"^(?:update|change|replace|correct|match|sync)(?:s|ed|ing)?$"),
        "sentence_object": re.compile(r"^(?:contacts?|details|record|directory|remittance|"
                                      r"emails?|supplier)$")},
    GoalType.export_invoices: {"verb": re.compile(r"^(?:export|csv|spreadsheet|download|excel)"
                                                  r"(?:s|ed|ing)?$"), "self_object": True},
}
CONFIRM_ACTION: dict[GoalType, str] = {
    GoalType.register_invoice: "register the invoice",
    GoalType.check_or_register_invoice: "check it and register the invoice if it is missing",
    GoalType.register_batch: "record the invoices",
    GoalType.update_supplier_contact: "update the supplier contact details",
    GoalType.export_invoices: "export the invoices",
}


def _sentences(request: str) -> list[tuple[list[str], bool]]:
    sentences, current = [], []
    for token in _TOKEN.findall(request):
        if token in ".;:!?":
            if current:
                sentences.append((current, token == "?"))
            current = []
        else:
            current.append(token)
    return sentences + ([(current, False)] if current else [])


def _action_negated(words: list[str], index: int) -> bool:
    # A prohibition can be separated from its verb by an adverbial phrase:
    # "Do not under any circumstances register...". Stop at another action or a
    # contrasting clause so "don't export; register the invoice" is allowed.
    for position in range(index - 1, -1, -1):
        if words[position] in {"but", "however", "instead"}:
            break
        if _ACTION_WORD.match(words[position]):
            break
        if words[position] in {"don't", "dont", "never", "avoid"}:
            return True
        if (words[position] == "not" and position > 0 and words[position - 1] == "do"):
            return True
    for position in range(max(0, index - 3), index):
        word = words[position]
        if word not in _NEGATION:
            continue
        # "If not, put it in" describes when to act; it does not forbid the action.
        if word == "not" and position > 0 and words[position - 1] == "if":
            continue
        if word in {"isn't", "hasn't", "aren't"} and "if" in words[max(0, position - 2):position]:
            continue
        return True
    return False


def action_evidence(goal_type: GoalType, request: str) -> str:
    rule = _GOAL_RULES[goal_type]
    latest_message = request.rsplit("\n", 1)[-1].strip().casefold()
    confirmed = latest_message == f"yes, {CONFIRM_ACTION[goal_type]}"
    other_object = (goal_type in {GoalType.register_invoice, GoalType.register_batch,
                                  GoalType.check_or_register_invoice}
                    and _OTHER_OBJECT.search(request.casefold()) is not None and not confirmed)
    unclear = denied = False
    for sentence, question in _sentences(request):
        lower = [token.casefold() for token in sentence]
        direct_request = lower[:2] in (["can", "you"], ["could", "you"],
                                       ["would", "you"], ["will", "you"])
        for index, word in enumerate(lower):
            if rule.get("unclear") and rule["unclear"].match(word):
                unclear = True
            if not rule["verb"].match(word):
                continue
            if index and lower[index - 1] in _DETERMINERS and not rule.get("self_object"):
                continue  # "the register", "on file": a noun, not an action
            if _action_negated(lower, index):
                denied = True
                continue
            if lower[max(0, index - 2):index] == ["before", "you"]:
                unclear = True
                continue
            if question and not direct_request:
                unclear = True
                continue
            if rule.get("self_object"):
                return "clear"
            if rule.get("sentence_object") and any(rule["sentence_object"].match(item)
                                                    for item in lower):
                return "clear"
            if "object" in rule:
                for token, item in zip(sentence[index + 1:index + 8], lower[index + 1:index + 8]):
                    if rule["object"].match(item):
                        return "unclear" if other_object else "clear"
                    if item in _FILLER or token[:1].isupper() or item.isdigit():
                        continue
                    break
            unclear = True
        if "object" in rule:
            # passive phrasing: "the newest invoice ... needs to go into the register"
            text = " ".join(lower)
            for match in re.finditer(r"\b(?:in|into|to) (?:our |the )?(?:register|books)\b", text):
                before = text[:match.start()].split()
                if not any(rule["object"].match(item) for item in before):
                    continue
                if not question and _PASSIVE_REGISTER.search(" ".join(before)):
                    if _NEGATION & set(before[-5:]):
                        denied = True
                    else:
                        return "unclear" if other_object else "clear"
                    continue
                unclear = True
    return "none" if denied else ("unclear" if unclear else "none")


def action_matches(goal_type: GoalType, request: str) -> bool:
    return action_evidence(goal_type, request) == "clear"


def numbers_in(request: str) -> set[int]:
    """Counts the user wrote, as digits or words."""
    text = request.casefold()
    found = {int(item) for item in re.findall(r"\b\d{1,3}\b", text)}
    found |= {value for word, value in NUMBER_WORDS.items() if re.search(rf"\b{word}\b", text)}
    return found


def dates_in(request: str) -> set[date]:
    """Dates the user wrote, in the common written forms, read day-first when numeric."""
    found = set()
    for match in DATE_PATTERN.findall(request.casefold()):
        cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", match).replace(",", "")
        cleaned = re.sub(r"\bof\s+", "", cleaned)
        cleaned = " ".join(cleaned.split())
        for fmt in DATE_FORMATS:
            try:
                found.add(datetime.strptime(cleaned, fmt).replace(tzinfo=UTC).date())
                break
            except ValueError:
                continue
    return found


async def commit_goal(
    proposal: GoalProposal | dict, request_text: str, probes, *, run_id: str,
) -> GoalContract | GoalRejection:
    if isinstance(proposal, dict):
        try:
            proposal = GoalProposal.model_validate(proposal)
        except ValueError:
            return GoalRejection("unsupported", "Request does not fit a supported goal type")
    request = request_text.casefold()
    evidence = action_evidence(proposal.goal_type, request_text)
    if evidence == "none":
        return GoalRejection("request_mismatch",
                             f"The request does not ask to {CONFIRM_ACTION[proposal.goal_type]}"
                             "; if the user wants a different kind of action, call unsupported, "
                             "and if it is unclear, ask the user")
    if evidence == "unclear":
        return GoalRejection("needs_confirmation",
                             f"The request does not clearly ask to {CONFIRM_ACTION[proposal.goal_type]}",
                             [f"Yes, {CONFIRM_ACTION[proposal.goal_type]}", "No"])
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

    if proposal.goal_type == GoalType.export_invoices and not supplier:
        named = [row for row in suppliers if any(
            re.search(rf"(?<!\w){re.escape(term.strip().casefold())}(?!\w)", request)
            for term in [row["name"], *row.get("aliases", "").split(",")] if term.strip()
        )]
        if named:
            if len(named) > 1:
                return GoalRejection("needs_clarification", "Export supplier is ambiguous",
                                     [row["name"] for row in named])
            return GoalRejection("request_mismatch", "Export must keep the named supplier filter")

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
    if latest_requested and (
        proposal.selector not in {"latest", None}
        or proposal.invoice_number and proposal.invoice_number.casefold() not in request
    ):
        return GoalRejection("request_mismatch",
                             "The request asks for the latest invoice; use selector latest "
                             "rather than a number the user did not give")
    if proposal.selector == "invoice_number" and (
        not proposal.invoice_number or proposal.invoice_number.casefold() not in request
    ):
        return GoalRejection("request_mismatch", "Invoice number must appear in request")
    if proposal.goal_type in {GoalType.register_invoice, GoalType.check_or_register_invoice}:
        requested_numbers = set(_INVOICE_NUMBER.findall(request.upper()))
        proposed_number = proposal.invoice_number.upper() if proposal.invoice_number else None
        if len(requested_numbers) > 1:
            return GoalRejection("needs_confirmation", "Which invoice number should be registered?",
                                 sorted(requested_numbers))
        if requested_numbers and (proposal.selector == "latest" or
                                  proposed_number not in requested_numbers):
            return GoalRejection("request_mismatch", "Proposed invoice differs from the request")
        if proposed_number and not requested_numbers:
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
        if not cap or cap < 1 or cap > 10 or cap not in numbers_in(request):
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
        if proposal.source_doc_id:
            try:
                message = await probes.portal_document(proposal.source_doc_id)
            except (LookupError, KeyError):
                return GoalRejection("blocked", "Source message not found")
        else:
            # like "latest" for invoices: code resolves the supplier's most recent contact message
            messages = [row for row in await probes.portal_messages(supplier_id)
                        if row.get("contact_name") or row.get("contact_email")]
            if not messages:
                return GoalRejection("blocked", "The supplier has sent no contact details on "
                                                "the portal")
            newest = max(row["date"] for row in messages)
            latest = [row for row in messages if row["date"] == newest]
            if len(latest) > 1:
                return GoalRejection("needs_clarification", "Several contact messages share the "
                                     "latest date", [row["doc_id"] for row in latest])
            message = latest[0]
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
        if not re.search(r"\bdue\s+before\b", request):
            return GoalRejection("request_mismatch", "Export requires a due-before request")
        if due not in dates_in(request):
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
