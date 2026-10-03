"""Isolated fake or budgeted live scenario runner."""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sqlite3
import tempfile
import time
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import uvicorn
import yaml
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse

from evals.controls import run_control
from evals.oracle import inspect_case
from evals.report import render_report
from evals.scripts import fake_script
from sandbox.portal.app import create_app as portal_app
from sandbox.register.app import create_app as register_app
from sandbox.register.db import connect
from worker.config import ROOT, Settings, load_pricing
from worker.contracts import Approval, Principal
from worker.llm.fake import FakeProvider
from worker.llm.ledger import Ledger
from worker.llm.provider import Provider
from worker.policy.approvals import decide_approval
from worker.runtime.loop import WorkerLoop
from worker.store import Store
from worker.tools.browser import BrowserSession
from worker.tools.files import WorkspaceFiles
from worker.verify.probes import Probes

SCENARIOS = Path(__file__).with_name("scenarios.yaml")
REPORT = Path(__file__).with_name("REPORT.md")
LIVE_REPORT = Path(__file__).with_name("LIVE_REPORT.md")


async def _serve(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(10)
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        await asyncio.sleep(0.01)
    return url, server, task


def _principal(user_id: str) -> Principal:
    return Principal(user_id=user_id, email=f"{user_id}@example.com",
                     display_name=user_id.title(), role="admin" if user_id == "asha" else "operator")


def _apply_fault(path: Path, fault: str | None) -> None:
    if not fault:
        return
    queries = {
        "fail_next_save": "UPDATE faults SET fail_next_save=1 WHERE id=1",
        "commit_then_timeout": "UPDATE faults SET commit_then_timeout=1 WHERE id=1",
        "corrupt_next_save": "UPDATE faults SET corrupt_next_save=1 WHERE id=1",
        "layout_b": "UPDATE faults SET layout_variant='b' WHERE id=1",
    }
    with connect(path) as db:
        db.execute(queries[fault])


async def run_case(case: dict, *, reference_date: date, live: bool = False,
                   ledger: Ledger | None = None, settings: Settings | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"centeralign-{case['id']}-") as directory:
        root = Path(directory)
        portal_db, register_db = root / "portal.db", root / "register.db"
        portal = portal_app(portal_db, reference_date=reference_date, probe_key="probe-demo")
        portal.add_api_route("/eval-offsite-redirect",
                             lambda: RedirectResponse("https://example.org/offsite", status_code=302),
                             methods=["GET"])
        portal_url, portal_server, portal_task = await _serve(portal)
        register_url, register_server, register_task = await _serve(register_app(
            register_db, reference_date=reference_date))
        browser = None
        probes = None
        provider = None
        try:
            _apply_fault(register_db, case.get("fault"))
            principal = _principal(case["principal"])
            browser = await BrowserSession.start(case["id"], principal,
                                                 portal_url=portal_url, register_url=register_url)
            cookies = await browser.context.cookies(register_url)
            register_session = next(item["value"] for item in cookies
                                    if item["name"] == "reg_session")
            workspace = root / "workspace"
            store = Store(root / "worker.db")
            probes = Probes(portal_url=portal_url, register_url=register_url,
                            probe_key="probe-demo", register_session=register_session,
                            workspace=workspace, store=store)
            if case["kind"] == "control":
                started = time.monotonic()
                result = await run_control(case, browser=browser, probes=probes,
                                           portal_url=portal_url, register_url=register_url,
                                           register_db=register_db)
                result["latency_s"] = time.monotonic() - started
                return result
            if live:
                provider = Provider(base_url=settings.base_url, api_key=settings.api_key,
                                    model=settings.model, ledger=ledger)
            else:
                provider = FakeProvider(fake_script(case, portal_url, register_url))
            store.create_run(case["id"], case["request"], principal, provider.model)
            worker = WorkerLoop(store=store, provider=provider, browser=browser,
                                probes=probes, workspace=WorkspaceFiles(workspace),
                                portal_url=portal_url, register_url=register_url)
            try:
                if case["kind"] == "crash":
                    if live:
                        raise ValueError("Crash recovery scenario uses the deterministic provider")
                    running = asyncio.create_task(worker.run(case["id"]))
                    try:
                        for _ in range(300):
                            await asyncio.sleep(0.02)
                            with sqlite3.connect(register_db) as db:
                                saved = db.execute("SELECT COUNT(*) FROM invoices "
                                                   "WHERE invoice_number='LS-1042'").fetchone()[0]
                            if saved == 1 and any(
                                item.state == "dispatching"
                                for item in store.pending_for_run(case["id"])
                            ):
                                break
                        else:
                            raise RuntimeError("Dispatch window was not reached")
                    finally:
                        running.cancel()
                        await asyncio.gather(running, return_exceptions=True)
                    await probes.close()
                    await browser.close()
                    store.update_run(case["id"], status="interrupted")
                    browser = await BrowserSession.start(case["id"], principal,
                                                         portal_url=portal_url,
                                                         register_url=register_url)
                    cookies = await browser.context.cookies(register_url)
                    register_session = next(item["value"] for item in cookies
                                            if item["name"] == "reg_session")
                    probes = Probes(portal_url=portal_url, register_url=register_url,
                                    probe_key="probe-demo", register_session=register_session,
                                    workspace=workspace, store=store)
                    worker = WorkerLoop(store=store, provider=FakeProvider([
                        {"tool": "finish", "arguments": {"summary": "Ready for verification"}},
                    ]), browser=browser, probes=probes,
                        workspace=WorkspaceFiles(workspace), portal_url=portal_url,
                        register_url=register_url)
                await worker.run(case["id"])
                if case.get("decision") and store.get_run(case["id"]).status == "awaiting_approval":
                    approval = store.approvals(case["id"])[0]
                    decided = decide_approval(Approval.model_validate(approval),
                                              case["decision"], principal.email)
                    store.save_approval(decided.approval_id, case["id"],
                                        decided.model_dump(mode="json"))
                    await worker.run(case["id"])
            except Exception as exc:  # noqa: BLE001 - preserve the case and report failure
                store.update_run(case["id"], status="failed", phase="done")
                store.append_event(case["id"], "error", {
                    "code": "eval_case_error", "message": type(exc).__name__, "retryable": False,
                })
            return inspect_case(case, store, case["id"], portal_db, register_db, workspace)
        finally:
            if probes:
                await probes.close()
            if browser:
                await browser.close()
            if live and provider:
                await provider.close()
            portal_server.should_exit = True
            register_server.should_exit = True
            await portal_task
            await register_task


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--limit", type=int)
    arguments = parser.parse_args()
    fixture = yaml.safe_load(SCENARIOS.read_text())
    cases = fixture["scenarios"][:arguments.limit] if arguments.limit else fixture["scenarios"]
    reference_date = date.fromisoformat(str(fixture["reference_date"]))
    ledger = None
    settings = None
    if arguments.live:
        load_dotenv(ROOT / ".env", override=False)
        settings = replace(Settings.from_env(), model="google/gemini-2.5-flash-lite")
        if not settings.api_key:
            raise SystemExit("AICREDITS_API_KEY must be configured locally for live eval")
        pricing = load_pricing()
        if os.getenv("LIMIT_INR"):
            pricing = replace(pricing, global_limit_inr=min(
                pricing.global_limit_inr, Decimal(os.environ["LIMIT_INR"])))
        ledger = Ledger(ROOT / "data" / "live-eval-ledger.db", pricing)
    results = []
    for case in cases:
        if arguments.live and (ledger.pricing.global_limit_inr - ledger.spent()
                               < ledger.pricing.run_limit_inr):
            break
        result = await run_case(case, reference_date=reference_date,
                                live=arguments.live, ledger=ledger, settings=settings)
        results.append(result)
        print(f"{case['id']}: {'PASS' if result['success'] else 'FAIL'} "
              f"({result['actual_status']}; ₹{result['cost_inr']})")
    report = render_report(results, model=settings.model if settings else "fake",
                           tier="live" if arguments.live else "fake",
                           reference_date=str(reference_date), seed=fixture["seed"])
    target = LIVE_REPORT if arguments.live else REPORT
    target.write_text(report)
    print(f"Report: {target}")


if __name__ == "__main__":
    asyncio.run(main())
