"""Per-user company memory: what each person meant when the worker had to ask.

Memory only ever suggests. A remembered choice is offered in the next question about the same
ambiguity; it never answers the question or changes a goal by itself, so the code rule that
ambiguity is resolved by the user still holds.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class Memory:
    def __init__(self, path: Path | str):
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS memory (user_id TEXT NOT NULL, "
                       "kind TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, "
                       "updated_at TEXT NOT NULL, PRIMARY KEY (user_id, kind, key))")

    @staticmethod
    def _key(text: str) -> str:
        return " ".join(text.casefold().split())

    def recall(self, user_id: str, kind: str, key: str) -> str | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT value FROM memory WHERE user_id=? AND kind=? AND key=?",
                             (user_id, kind, self._key(key))).fetchone()
        return row[0] if row else None

    def remember(self, user_id: str, kind: str, key: str, value: str) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO memory VALUES (?,?,?,?,?) ON CONFLICT(user_id, kind, key) "
                       "DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                       (user_id, kind, self._key(key), value, datetime.now(UTC).isoformat()))


def chosen_candidate(answer: str, candidates: list[str]) -> str | None:
    """The single candidate the answer names, if exactly one is named."""
    text = answer.casefold()
    named = [item for item in candidates if item.casefold() in text]
    exact = [item for item in candidates if item.casefold() == text.strip()]
    if exact:
        return exact[0]
    return named[0] if len(named) == 1 else None
