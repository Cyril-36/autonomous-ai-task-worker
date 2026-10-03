"""Local demo identities shared with the register seed."""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Request

from sandbox.common.seed import ASSIGNMENTS, SUPPLIERS, USERS
from worker.contracts import Principal


class DemoAuth:
    def __init__(self, passwords: dict[str, str] | None = None):
        self.passwords = passwords or {
            "asha@example.com": os.getenv("ASHA_PASSWORD", "asha-demo"),
            "ravi@example.com": os.getenv("RAVI_PASSWORD", "ravi-demo"),
            "meera@example.com": os.getenv("MEERA_PASSWORD", "meera-demo"),
        }
        self.sessions: dict[str, Principal] = {}

    def users(self) -> list[dict]:
        names = {supplier_id: name for supplier_id, name, _ in SUPPLIERS}
        return [
            {
                "email": email, "display_name": display_name, "role": role,
                "assigned_suppliers": [names[supplier_id] for user_id, supplier_id in ASSIGNMENTS
                                       if user_id == uid],
                "password_hint": "Use the local demo password",
            }
            for uid, email, display_name, role in USERS
        ]

    def sign_in(self, email: str, password: str) -> tuple[Principal, str]:
        expected = self.passwords.get(email)
        if not expected or not secrets.compare_digest(password, expected):
            raise HTTPException(401, detail=("bad_credentials", "Invalid email or password"))
        uid, _, display_name, role = next(row for row in USERS if row[1] == email)
        principal = Principal(user_id=uid, email=email, display_name=display_name, role=role)
        token = secrets.token_urlsafe(32)
        self.sessions[token] = principal
        return principal, token

    def current(self, request: Request) -> Principal:
        token = request.cookies.get("console_session", "")
        principal = self.sessions.get(token)
        if not principal:
            raise HTTPException(401, detail=("not_signed_in", "Sign in required"))
        return principal

    def sign_out(self, request: Request) -> None:
        self.sessions.pop(request.cookies.get("console_session", ""), None)
