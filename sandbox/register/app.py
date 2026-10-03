"""Internal register: HTML and API writes share authorization and operations."""

from __future__ import annotations

import asyncio
import os
import secrets
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from sandbox.register.authz import require_admin, require_assigned
from sandbox.register.db import connect, init_db
from sandbox.register.operations import assert_issued, issue, operation, settle, void

TEMPLATES = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)


def create_app(
    db_path: Path | str | None = None, *, reference_date: date | None = None,
    passwords: dict[str, str] | None = None, timeout_delay: float = 6,
) -> FastAPI:
    path = Path(db_path or os.getenv("REGISTER_DB", "data/register.db"))
    today = datetime.now(UTC).date()
    init_db(path, reference_date or date.fromisoformat(os.getenv("DEMO_REFERENCE_DATE", today.isoformat())))
    user_passwords = passwords or {
        "asha@example.com": os.getenv("ASHA_PASSWORD", "asha-demo"),
        "ravi@example.com": os.getenv("RAVI_PASSWORD", "ravi-demo"),
        "meera@example.com": os.getenv("MEERA_PASSWORD", "meera-demo"),
    }
    sessions: dict[str, str] = {}
    app = FastAPI(title="Halden invoice register")

    def principal(request: Request, *, api: bool = False) -> str:
        bearer = request.headers.get("authorization", "")
        token = bearer[7:] if api and bearer.startswith("Bearer ") else request.cookies.get("reg_session")
        user_id = sessions.get(token or "")
        if not user_id:
            raise HTTPException(401, "Sign in required")
        return user_id

    def all_rows(query: str, params: tuple = ()) -> list[dict]:
        with connect(path) as db:
            return [dict(row) for row in db.execute(query, params)]

    def one_row(query: str, params: tuple = ()) -> dict:
        found = all_rows(query, params)
        if not found:
            raise HTTPException(404, "Record not found")
        return found[0]

    async def save_invoice(data: dict[str, str], user_id: str, *, record_id: int | None = None) -> int:
        token = data.get("form_token", "")
        status_error: HTTPException | None = None
        should_timeout = False
        saved_id = 0
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            assert_issued(db, token)
            if record_id is None:
                supplier_id = data.get("supplier_id", "")
            else:
                existing = db.execute("SELECT * FROM invoices WHERE id=?", (record_id,)).fetchone()
                if not existing:
                    raise HTTPException(404, "Invoice not found")
                supplier_id = existing["supplier_id"]
            require_assigned(db, user_id, supplier_id)
            supplier = db.execute("SELECT 1 FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
            if not supplier:
                raise HTTPException(422, "Unknown supplier")
            try:
                amount = f"{Decimal(data['amount']):.2f}"
                if Decimal(amount) < 0:
                    raise ValueError
                due = date.fromisoformat(data["due_date"])
            except (KeyError, InvalidOperation, ValueError) as exc:
                raise HTTPException(422, "Invalid amount or due date") from exc
            values = {
                "supplier_id": supplier_id, "invoice_number": data.get("invoice_number", ""),
                "amount": amount, "currency": data.get("currency", ""),
                "due_date": due.isoformat(), "source_doc_id": data.get("source_doc_id", ""),
            }
            if not values["invoice_number"] or not values["currency"] or not values["source_doc_id"]:
                raise HTTPException(422, "Required invoice field missing")
            fault = db.execute("SELECT * FROM faults WHERE id=1").fetchone()
            if fault["fail_next_save"]:
                db.execute("UPDATE faults SET fail_next_save=0 WHERE id=1")
                settle(db, token, "rejected")
                status_error = HTTPException(503, "Transient save failure")
            else:
                if fault["corrupt_next_save"]:
                    values["due_date"] = (due + timedelta(days=1)).isoformat()
                    db.execute("UPDATE faults SET corrupt_next_save=0 WHERE id=1")
                if record_id is None:
                    duplicate = db.execute(
                        "SELECT id FROM invoices WHERE supplier_id=? AND invoice_number=?",
                        (supplier_id, values["invoice_number"]),
                    ).fetchone()
                    if duplicate:
                        settle(db, token, "rejected")
                        status_error = HTTPException(409, "Invoice number already exists for supplier")
                    else:
                        cursor = db.execute(
                            "INSERT INTO invoices(supplier_id,invoice_number,amount,currency,due_date,source_doc_id,created_by) VALUES (?,?,?,?,?,?,?)",
                            (*values.values(), user_id),
                        )
                        saved_id = cursor.lastrowid
                else:
                    if str(existing["version"]) != data.get("version"):
                        settle(db, token, "rejected")
                        status_error = HTTPException(409, "Stale invoice version")
                    else:
                        db.execute(
                            "UPDATE invoices SET invoice_number=?,amount=?,currency=?,due_date=?,source_doc_id=?,version=version+1 WHERE id=?",
                            (values["invoice_number"], values["amount"], values["currency"],
                             values["due_date"], values["source_doc_id"], record_id),
                        )
                        saved_id = record_id
                if saved_id:
                    settle(db, token, "committed", str(saved_id),
                           dict(existing) if record_id is not None else None, values)
                    if fault["commit_then_timeout"]:
                        db.execute("UPDATE faults SET commit_then_timeout=0 WHERE id=1")
                        should_timeout = True
        if status_error:
            raise status_error
        if should_timeout:
            await asyncio.sleep(timeout_delay)
        return saved_id

    @app.get("/login", response_class=HTMLResponse)
    def login_page():
        return "<h1>Register sign in</h1><form method='post'><input name='email'><input type='password' name='password'><button>Sign in</button></form>"

    @app.post("/login")
    async def login(request: Request):
        form = await request.form()
        email = str(form.get("email", ""))
        password = str(form.get("password", ""))
        if email not in user_passwords or not secrets.compare_digest(password, user_passwords[email]):
            raise HTTPException(401, "Invalid credentials")
        user = one_row("SELECT id FROM users WHERE email=?", (email,))
        token = secrets.token_urlsafe(32)
        sessions[token] = user["id"]
        response = RedirectResponse("/invoices", status_code=303)
        response.set_cookie("reg_session", token, httponly=True, samesite="lax")
        return response

    @app.get("/invoices", response_class=HTMLResponse)
    def invoice_list(request: Request, supplier_id: str | None = None, due_before: str | None = None):
        principal(request)
        rows = all_rows("SELECT * FROM invoices ORDER BY id")
        if supplier_id:
            rows = [row for row in rows if row["supplier_id"] == supplier_id]
        if due_before:
            rows = [row for row in rows if row["due_date"] < due_before]
        return TEMPLATES.get_template("list.html").render(rows=rows)

    @app.get("/invoices/new", response_class=HTMLResponse)
    def new_invoice(request: Request):
        principal(request)
        with connect(path) as db:
            token = issue(db)
            variant = db.execute("SELECT layout_variant FROM faults WHERE id=1").fetchone()[0]
        return TEMPLATES.get_template("invoice_form.html").render(
            token=token, record=None, suppliers=all_rows("SELECT * FROM suppliers ORDER BY name"),
            variant=variant,
        )

    @app.post("/invoices")
    async def create_invoice(request: Request):
        user_id = principal(request)
        saved_id = await save_invoice(dict(await request.form()), user_id)
        return RedirectResponse(f"/invoices/{saved_id}", status_code=303)

    @app.get("/invoices/{record_id}", response_class=HTMLResponse)
    def invoice_detail(record_id: int, request: Request):
        principal(request)
        record = one_row("SELECT * FROM invoices WHERE id=?", (record_id,))
        return TEMPLATES.get_template("detail.html").render(record=record)

    @app.get("/invoices/{record_id}/edit", response_class=HTMLResponse)
    def invoice_edit(record_id: int, request: Request):
        user_id = principal(request)
        with connect(path) as db:
            record = db.execute("SELECT * FROM invoices WHERE id=?", (record_id,)).fetchone()
            if not record:
                raise HTTPException(404, "Invoice not found")
            require_assigned(db, user_id, record["supplier_id"])
            token = issue(db)
            variant = db.execute("SELECT layout_variant FROM faults WHERE id=1").fetchone()[0]
        return TEMPLATES.get_template("invoice_form.html").render(
            token=token, record=dict(record), suppliers=all_rows("SELECT * FROM suppliers ORDER BY name"),
            variant=variant,
        )

    @app.post("/invoices/{record_id}")
    async def update_invoice(record_id: int, request: Request):
        saved_id = await save_invoice(dict(await request.form()), principal(request), record_id=record_id)
        return RedirectResponse(f"/invoices/{saved_id}", status_code=303)

    @app.get("/suppliers", response_class=HTMLResponse)
    def suppliers(request: Request):
        principal(request)
        rows = all_rows("SELECT * FROM suppliers ORDER BY name")
        return "<h1>Suppliers</h1><ul>" + "".join(
            f'<li><a href="/suppliers/{row["id"]}">{row["name"]}</a></li>' for row in rows
        ) + "</ul>"

    @app.get("/suppliers/{supplier_id}", response_class=HTMLResponse)
    def supplier_detail(supplier_id: str, request: Request):
        principal(request)
        row = one_row("SELECT * FROM suppliers WHERE id=?", (supplier_id,))
        return TEMPLATES.get_template("supplier.html").render(row=row, token=None)

    @app.get("/suppliers/{supplier_id}/edit", response_class=HTMLResponse)
    def supplier_edit(supplier_id: str, request: Request):
        user_id = principal(request)
        with connect(path) as db:
            require_assigned(db, user_id, supplier_id)
            token = issue(db)
        row = one_row("SELECT * FROM suppliers WHERE id=?", (supplier_id,))
        return TEMPLATES.get_template("supplier.html").render(row=row, token=token)

    @app.post("/suppliers/{supplier_id}")
    async def update_supplier(supplier_id: str, request: Request):
        user_id = principal(request)
        data = dict(await request.form())
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            assert_issued(db, data.get("form_token", ""))
            require_assigned(db, user_id, supplier_id)
            old = db.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
            if not old:
                raise HTTPException(404, "Supplier not found")
            if data.get("version") != str(old["version"]):
                settle(db, data["form_token"], "rejected")
                raise HTTPException(409, "Stale supplier version")
            changes = {field: str(data.get(field, old[field])) for field in
                       ("contact_name", "contact_email", "remittance_email")}
            db.execute(
                "UPDATE suppliers SET contact_name=?,contact_email=?,remittance_email=?,version=version+1 WHERE id=?",
                (*changes.values(), supplier_id),
            )
            settle(db, data["form_token"], "committed", supplier_id, dict(old), changes)
        return RedirectResponse(f"/suppliers/{supplier_id}", status_code=303)

    @app.get("/policy", response_class=HTMLResponse)
    def policy_page(request: Request):
        principal(request)
        row = one_row("SELECT * FROM policy WHERE id=1")
        return f'<h1>Policy</h1><p>Approval threshold ₹{row["threshold"]}</p>'

    @app.post("/policy")
    async def update_policy(request: Request):
        user_id = principal(request)
        data = dict(await request.form())
        with connect(path) as db:
            require_admin(db, user_id)
            db.execute("UPDATE policy SET threshold=?,version=version+1 WHERE id=1",
                       (data.get("threshold", "100000.00"),))
        return {"ok": True}

    @app.post("/admin/assignments")
    async def update_assignments(request: Request):
        user_id = principal(request)
        data = dict(await request.form())
        with connect(path) as db:
            require_admin(db, user_id)
            db.execute("INSERT OR IGNORE INTO assignments VALUES (?,?)",
                       (data.get("user_id"), data.get("supplier_id")))
        return {"ok": True}

    @app.get("/api/invoices")
    def api_invoices(request: Request, supplier_id: str | None = None, due_before: str | None = None):
        principal(request, api=True) if request.headers.get("authorization") else principal(request)
        rows = all_rows("SELECT * FROM invoices ORDER BY id")
        return [row for row in rows if (not supplier_id or row["supplier_id"] == supplier_id)
                and (not due_before or row["due_date"] < due_before)]

    @app.post("/api/invoices", status_code=201)
    async def api_create_invoice(request: Request):
        user_id = principal(request, api=True)
        saved_id = await save_invoice(await request.json(), user_id)
        return one_row("SELECT * FROM invoices WHERE id=?", (saved_id,))

    @app.get("/api/suppliers")
    def api_suppliers(request: Request):
        principal(request, api=True) if request.headers.get("authorization") else principal(request)
        return all_rows("SELECT * FROM suppliers ORDER BY name")

    @app.get("/api/policy")
    def api_policy(request: Request):
        principal(request, api=True) if request.headers.get("authorization") else principal(request)
        return one_row("SELECT * FROM policy WHERE id=1")

    @app.get("/api/operations/{token}")
    def api_operation(token: str, request: Request):
        principal(request, api=True)
        with connect(path) as db:
            return operation(db, token)

    @app.post("/api/operations/{token}/void")
    def api_void(token: str, request: Request):
        principal(request, api=True)
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            return void(db, token)

    @app.post("/api/_faults")
    async def api_faults(request: Request):
        user_id = principal(request, api=True)
        values = await request.json()
        allowed = {"fail_next_save", "corrupt_next_save", "commit_then_timeout",
                   "layout_variant", "slow_pages"}
        if not isinstance(values, dict) or set(values) - allowed:
            raise HTTPException(422, "Invalid fault switch")
        with connect(path) as db:
            require_admin(db, user_id)
            for key, value in values.items():
                db.execute(f"UPDATE faults SET {key}=? WHERE id=1", (value,))
        return {"ok": True}

    return app


app = create_app()
