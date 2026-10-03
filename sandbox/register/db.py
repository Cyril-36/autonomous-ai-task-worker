"""SQLite schema and deterministic seed for the internal register."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from sandbox.common.seed import ASSIGNMENTS, SUPPLIERS, USERS, invoice_seed


def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db(path: Path, reference_date: date) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS suppliers (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, aliases TEXT NOT NULL,
                contact_name TEXT NOT NULL DEFAULT '', contact_email TEXT NOT NULL DEFAULT '',
                remittance_email TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL, role TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS assignments (
                user_id TEXT NOT NULL, supplier_id TEXT NOT NULL,
                PRIMARY KEY (user_id, supplier_id)
            );
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id TEXT NOT NULL, invoice_number TEXT NOT NULL,
                amount TEXT NOT NULL, currency TEXT NOT NULL, due_date TEXT NOT NULL,
                source_doc_id TEXT NOT NULL, created_by TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                UNIQUE (supplier_id, invoice_number)
            );
            CREATE TABLE IF NOT EXISTS policy (
                id INTEGER PRIMARY KEY CHECK (id=1), version INTEGER NOT NULL,
                threshold TEXT NOT NULL, invoice_update_approval INTEGER NOT NULL,
                remittance_change_approval INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS operations (
                form_token TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK(status IN ('issued','committed','rejected','voided')),
                record_id TEXT, before_json TEXT, after_json TEXT
            );
            CREATE TABLE IF NOT EXISTS faults (
                id INTEGER PRIMARY KEY CHECK (id=1),
                fail_next_save INTEGER NOT NULL DEFAULT 0,
                corrupt_next_save INTEGER NOT NULL DEFAULT 0,
                commit_then_timeout INTEGER NOT NULL DEFAULT 0,
                layout_variant TEXT NOT NULL DEFAULT 'a',
                slow_pages INTEGER NOT NULL DEFAULT 0
            );
        """)
        if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return
        db.executemany("INSERT INTO suppliers(id,name,aliases) VALUES (?,?,?)", SUPPLIERS)
        db.executemany("INSERT INTO users VALUES (?,?,?,?)", USERS)
        db.executemany("INSERT INTO assignments VALUES (?,?)", ASSIGNMENTS)
        db.execute("INSERT INTO policy VALUES (1,1,'100000.00',1,1)")
        db.execute("INSERT INTO faults(id) VALUES (1)")
        fixtures = invoice_seed(reference_date)
        for number in ("LS-1039", "BF-2291", "KC-701"):
            row = next(item for item in fixtures if item["invoice_number"] == number)
            db.execute(
                "INSERT INTO invoices(supplier_id,invoice_number,amount,currency,due_date,source_doc_id,created_by) VALUES (?,?,?,?,?,?,?)",
                (row["supplier_id"], number, row["amount"], row["currency"],
                 row["due_date"], row["doc_id"], "asha"),
            )
