"""Read-only supplier portal with an isolated probe API."""

from __future__ import annotations

import os
import secrets
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from sandbox.common.seed import invoice_seed, message_seed

TEMPLATES = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)


def indian_amount(value: str) -> str:
    whole, fraction = value.split(".")
    if len(whole) > 3:
        tail, front = whole[-3:], whole[:-3]
        groups = []
        while front:
            groups.insert(0, front[-2:])
            front = front[:-2]
        whole = ",".join([*groups, tail])
    return f"₹{whole}.{fraction}"


def init_db(path: Path, reference_date: date) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS invoices (
                doc_id TEXT PRIMARY KEY, revision TEXT NOT NULL, supplier_id TEXT NOT NULL,
                supplier TEXT NOT NULL, invoice_number TEXT NOT NULL,
                issue_date TEXT NOT NULL, due_date TEXT NOT NULL, amount TEXT NOT NULL,
                currency TEXT NOT NULL, notes TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                doc_id TEXT PRIMARY KEY, revision TEXT NOT NULL, supplier_id TEXT NOT NULL,
                supplier TEXT NOT NULL, sender TEXT NOT NULL, subject TEXT NOT NULL,
                date TEXT NOT NULL, contact_name TEXT NOT NULL, contact_email TEXT NOT NULL,
                remittance_email TEXT NOT NULL, body TEXT NOT NULL
            );
        """)
        if not db.execute("SELECT 1 FROM invoices LIMIT 1").fetchone():
            for row in invoice_seed(reference_date):
                db.execute(
                    "INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?)", tuple(row.values())
                )
            for row in message_seed(reference_date):
                db.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?)", tuple(row.values()))


def create_app(
    db_path: Path | str | None = None, *, reference_date: date | None = None,
    password: str | None = None, probe_key: str | None = None,
) -> FastAPI:
    path = Path(db_path or os.getenv("PORTAL_DB", "data/portal.db"))
    today = datetime.now(UTC).date()
    init_db(path, reference_date or date.fromisoformat(os.getenv("DEMO_REFERENCE_DATE", today.isoformat())))
    expected_password = password or os.getenv("PORTAL_PASSWORD", "portal-demo")
    expected_probe_key = probe_key or os.getenv("PROBE_KEY", "probe-demo")
    sessions: set[str] = set()
    app = FastAPI(title="Halden supplier portal")

    def rows(table: str, where: str = "", params: tuple = ()) -> list[dict]:
        with sqlite3.connect(path) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(f"SELECT * FROM {table} {where}", params)]

    def signed_in(request: Request) -> None:
        if request.cookies.get("portal_session") not in sessions:
            raise HTTPException(401, "Sign in to the supplier portal")

    def probe_authorized(key: str | None) -> None:
        if not key or not secrets.compare_digest(key, expected_probe_key):
            raise HTTPException(403, "Probe access denied")

    @app.get("/login", response_class=HTMLResponse)
    def login_page():
        return "<h1>Supplier portal sign in</h1><form method='post'><input type='password' name='password'><button>Sign in</button></form>"

    @app.post("/login")
    def login(password_value: str = Form(alias="password")):
        if not secrets.compare_digest(password_value, expected_password):
            raise HTTPException(401, "Invalid portal password")
        token = secrets.token_urlsafe(32)
        sessions.add(token)
        response = RedirectResponse("/invoices", status_code=303)
        response.set_cookie("portal_session", token, httponly=True, samesite="lax")
        return response

    @app.get("/invoices", response_class=HTMLResponse)
    def invoices(request: Request, page: int = 1, supplier: str = ""):
        signed_in(request)
        page = max(page, 1)
        all_rows = rows("invoices", "ORDER BY issue_date DESC, invoice_number")
        if supplier:
            all_rows = [row for row in all_rows if supplier.casefold() in row["supplier"].casefold()]
        return TEMPLATES.get_template("list.html").render(
            title="Invoices", rows=all_rows[(page - 1) * 10:page * 10],
            next_page=page + 1 if len(all_rows) > page * 10 else None,
            page=page, supplier=supplier,
        )

    @app.get("/invoices/{doc_id}", response_class=HTMLResponse)
    def invoice_detail(doc_id: str, request: Request):
        signed_in(request)
        found = rows("invoices", "WHERE doc_id=?", (doc_id,))
        if not found:
            raise HTTPException(404, "Invoice not found")
        row = found[0]
        fields = [
            ("Supplier", row["supplier"]), ("Invoice number", row["invoice_number"]),
            ("Issue date", date.fromisoformat(row["issue_date"]).strftime("%-d %b %Y")),
            ("Due date", date.fromisoformat(row["due_date"]).strftime("%-d %b %Y")),
            ("Amount", indian_amount(row["amount"])), ("Currency", row["currency"]),
            ("Notes", row["notes"]),
        ]
        return TEMPLATES.get_template("detail.html").render(row=row, fields=fields, kind="invoice")

    @app.get("/messages", response_class=HTMLResponse)
    def messages(request: Request):
        signed_in(request)
        return TEMPLATES.get_template("list.html").render(
            title="Messages", rows=rows("messages", "ORDER BY date DESC"),
            next_page=None, page=1, supplier="",
        )

    @app.get("/messages/{doc_id}", response_class=HTMLResponse)
    def message_detail(doc_id: str, request: Request):
        signed_in(request)
        found = rows("messages", "WHERE doc_id=?", (doc_id,))
        if not found:
            raise HTTPException(404, "Message not found")
        row = found[0]
        fields = [
            ("From", row["sender"]), ("Supplier", row["supplier"]),
            ("Subject", row["subject"]), ("Date", row["date"]),
            ("Contact name", row["contact_name"]), ("Contact email", row["contact_email"]),
            ("Remittance email", row["remittance_email"]), ("Body", row["body"]),
        ]
        return TEMPLATES.get_template("detail.html").render(row=row, fields=fields, kind="message")

    @app.get("/api/invoices")
    def probe_invoices(supplier_id: str | None = None, x_probe_key: str | None = Header(None)):
        probe_authorized(x_probe_key)
        return rows("invoices", "WHERE supplier_id=?" if supplier_id else "", (supplier_id,) if supplier_id else ())

    @app.get("/api/documents/{doc_id}")
    def probe_document(doc_id: str, x_probe_key: str | None = Header(None)):
        probe_authorized(x_probe_key)
        for table in ("invoices", "messages"):
            found = rows(table, "WHERE doc_id=?", (doc_id,))
            if found:
                return found[0]
        raise HTTPException(404, "Document not found")

    return app


app = create_app()
