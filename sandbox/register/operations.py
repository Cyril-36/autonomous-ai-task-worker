"""Server-issued single-use form operations."""

from __future__ import annotations

import json
import secrets
import sqlite3

from fastapi import HTTPException


def issue(db: sqlite3.Connection) -> str:
    token = secrets.token_urlsafe(24)
    db.execute("INSERT INTO operations(form_token,status) VALUES (?, 'issued')", (token,))
    return token


def assert_issued(db: sqlite3.Connection, token: str) -> None:
    row = db.execute("SELECT status FROM operations WHERE form_token=?", (token,)).fetchone()
    if not row or row[0] != "issued":
        raise HTTPException(409, "Form token already used or voided")


def settle(
    db: sqlite3.Connection, token: str, status: str, record_id: str | None = None,
    before: dict | None = None, after: dict | None = None,
) -> None:
    db.execute(
        "UPDATE operations SET status=?,record_id=?,before_json=?,after_json=? WHERE form_token=?",
        (status, record_id, json.dumps(before) if before else None,
         json.dumps(after) if after else None, token),
    )


def operation(db: sqlite3.Connection, token: str) -> dict:
    row = db.execute("SELECT * FROM operations WHERE form_token=?", (token,)).fetchone()
    if not row:
        raise HTTPException(404, "Operation not found")
    return {
        "status": row["status"], "record_id": row["record_id"],
        "before": json.loads(row["before_json"]) if row["before_json"] else None,
        "after": json.loads(row["after_json"]) if row["after_json"] else None,
    }


def void(db: sqlite3.Connection, token: str) -> dict:
    db.execute(
        "UPDATE operations SET status='voided' WHERE form_token=? AND status='issued'", (token,)
    )
    return operation(db, token)
