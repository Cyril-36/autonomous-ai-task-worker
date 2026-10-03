"""Read-only verifier probes outside the model's browser tools."""

from __future__ import annotations

import csv
from pathlib import Path

import httpx


class CsvRows(list):
    def __init__(self, rows: list[dict[str, str]], columns: list[str]):
        super().__init__(rows)
        self.columns = columns


class Probes:
    def __init__(
        self, *, portal_url: str = "http://127.0.0.1:8101",
        register_url: str = "http://127.0.0.1:8102", probe_key: str,
        register_session: str, workspace: Path | str, store=None,
    ):
        self.portal_url = portal_url
        self.register_url = register_url
        self.probe_key = probe_key
        self.register_session = register_session
        self.workspace = Path(workspace).resolve()
        self.store = store
        self.client = httpx.AsyncClient(timeout=15)

    async def close(self) -> None:
        await self.client.aclose()

    async def _portal(self, path: str, params: dict | None = None):
        response = await self.client.get(
            f"{self.portal_url}{path}", params=params,
            headers={"X-Probe-Key": self.probe_key},
        )
        response.raise_for_status()
        return response.json()

    async def _register(self, method: str, path: str, params: dict | None = None):
        response = await self.client.request(
            method, f"{self.register_url}{path}", params=params,
            headers={"Authorization": f"Bearer {self.register_session}"},
        )
        response.raise_for_status()
        return response.json()

    async def portal_invoices(self, supplier_id: str | None = None):
        return await self._portal("/api/invoices", {"supplier_id": supplier_id} if supplier_id else None)

    async def portal_messages(self, supplier_id: str | None = None):
        return await self._portal("/api/messages", {"supplier_id": supplier_id} if supplier_id else None)

    async def portal_document(self, doc_id: str):
        return await self._portal(f"/api/documents/{doc_id}")

    async def register_invoices(self, supplier_id: str | None = None,
                                due_before: str | None = None):
        params = {}
        if supplier_id:
            params["supplier_id"] = supplier_id
        if due_before:
            params["due_before"] = due_before
        return await self._register("GET", "/api/invoices", params)

    async def register_suppliers(self):
        return await self._register("GET", "/api/suppliers")

    async def register_supplier(self, supplier_id: str):
        return next(row for row in await self.register_suppliers() if row["id"] == supplier_id)

    async def register_policy(self):
        return await self._register("GET", "/api/policy")

    async def operation_status(self, token: str):
        return await self._register("GET", f"/api/operations/{token}")

    async def void_operation(self, token: str):
        return await self._register("POST", f"/api/operations/{token}/void")

    async def invoice_by_key(self, target_key: dict[str, str]):
        rows = await self.register_invoices(supplier_id=target_key["supplier_id"])
        return next((row for row in rows if row["invoice_number"] == target_key["invoice_number"]),
                    None)

    async def target_by_key(self, target_key: dict[str, str]):
        if "invoice_number" in target_key:
            return await self.invoice_by_key(target_key)
        return await self.register_supplier(target_key["supplier_id"])

    async def workspace_csv(self, path: str) -> list[dict[str, str]] | None:
        target = (self.workspace / path).resolve()
        if not target.is_relative_to(self.workspace) or not target.is_file():
            return None
        with target.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            return CsvRows(list(reader), reader.fieldnames or [])

    async def approval_recorded(self, run_id: str) -> bool:
        return bool(self.store and any(
            row.get("status") in {"approved", "used"}
            for row in self.store.approvals(run_id)
        ))
