"""The answer the user reads: rendered from the locked goal, the recorded facts and the
verification result. No model text reaches it."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from worker.contracts import GoalType


def _inr(value: str) -> str:
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return value
    whole, frac = f"{amount:.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "₹" + ",".join(groups + [tail]) + "." + frac if groups else f"₹{tail}.{frac}"


def _day(value: str) -> str:
    try:
        day = date.fromisoformat(value)
        return f"{day.day} {day.strftime('%b %Y')}"
    except ValueError:
        return value


def _invoice(source, facts: dict) -> str:
    amount = facts.get(f"{source.doc_id}.amount")
    due = facts.get(f"{source.doc_id}.due_date")
    parts = [source.key]
    if amount:
        parts.append(_inr(amount.normalized))
    if due:
        parts.append("due " + _day(due.normalized))
    return parts[0] + (" (" + ", ".join(parts[1:]) + ")" if len(parts) > 1 else "")


def describe_outcome(contract, facts: dict, result, *, export_path: str | None = None,
                     export_rows: int | None = None) -> str:
    """One or two plain sentences saying what was done, then how it was checked."""
    passed = sum(check.passed for check in result.checks)
    checked = f"{passed} of {len(result.checks)} checks passed on read-back."
    if not result.passed:
        failed = "; ".join(check.description for check in result.checks if not check.passed)
        return f"Not done: {failed}. {checked}"
    supplier = contract.supplier_name or "the supplier"
    goal = contract.goal_type
    if goal == GoalType.export_invoices:
        rows = f"{export_rows} invoices" if export_rows is not None else "the matching invoices"
        due = (contract.filter or {}).get("due_before", "")
        text = f"Exported {rows} due before {_day(due)} to {export_path or 'the exports folder'}."
    elif any(item.kind == "no_write" for item in contract.obligations):
        keys = ", ".join(source.key for source in contract.sources)
        text = (f"{keys} from {supplier} was already in the register with matching values, "
                "so nothing was changed.")
    elif goal == GoalType.update_supplier_contact:
        doc = contract.sources[0].doc_id
        values = [facts[key].normalized for key in sorted(facts)
                  if key.startswith((doc + ".contact_", doc + ".remittance_"))]
        text = f"Updated {supplier}'s contact details" + (
            ": " + ", ".join(values) + "." if values else ".")
    elif goal == GoalType.sync_existing_invoice:
        keys = ", ".join(source.key for source in contract.sources)
        text = f"Corrected existing invoice {keys} for {supplier} to match its portal source."
    else:
        saved = "; ".join(_invoice(source, facts) for source in contract.sources)
        noun = "invoice" if len(contract.sources) == 1 else f"{len(contract.sources)} invoices"
        text = f"Saved {noun} from {supplier} to the register: {saved}."
        if contract.batch_remaining:
            text += (" Left for later because of the cap: "
                     + ", ".join(source.key for source in contract.batch_remaining) + ".")
    return f"{text} {checked}"
