"""Strict normalization for source-derived obligation fields."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from worker.contracts import FactType

PLAIN = re.compile(r"\d+(?:\.\d{1,2})?")
WESTERN = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?")
INDIAN = re.compile(r"\d{1,3}(?:,\d{2})+,\d{3}(?:\.\d{1,2})?")


def normalize(value: str, kind: FactType | str) -> str:
    if kind == FactType.text or kind == "text":
        return value.strip()
    if kind == FactType.amount or kind == "amount":
        raw = value.strip()
        raw = re.sub(r"^(?:₹|Rs\.?|INR)\s*", "", raw, flags=re.IGNORECASE)
        if not any(pattern.fullmatch(raw) for pattern in (PLAIN, WESTERN, INDIAN)):
            raise ValueError("Invalid amount grouping or precision")
        try:
            number = Decimal(raw.replace(",", ""))
        except InvalidOperation as exc:
            raise ValueError("Invalid amount") from exc
        if number < 0:
            raise ValueError("Negative amount")
        return f"{number:.2f}"
    if kind == FactType.date or kind == "date":
        raw = value.strip()
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                parsed = date.fromisoformat(raw)
            elif re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", raw):
                parsed = datetime.strptime(raw, "%d/%m/%Y").replace(tzinfo=UTC).date()
            else:
                parsed = datetime.strptime(raw, "%d %b %Y").replace(tzinfo=UTC).date()
        except ValueError as exc:
            raise ValueError("Invalid date") from exc
        return parsed.isoformat()
    raise ValueError(f"Unknown fact type: {kind}")
