"""One authorization service for HTML and direct API writes."""

from __future__ import annotations

import sqlite3

from fastapi import HTTPException


def require_assigned(db: sqlite3.Connection, user_id: str, supplier_id: str) -> None:
    role = db.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
    if not role:
        raise HTTPException(401, "Sign in required")
    if role[0] == "admin":
        return
    assigned = db.execute(
        "SELECT 1 FROM assignments WHERE user_id=? AND supplier_id=?", (user_id, supplier_id)
    ).fetchone()
    if not assigned:
        raise HTTPException(403, "This supplier is not assigned to your account")


def require_admin(db: sqlite3.Connection, user_id: str) -> None:
    role = db.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
    if not role or role[0] != "admin":
        raise HTTPException(403, "Admin role required")
