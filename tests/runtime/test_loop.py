import asyncio
import csv
import socket
from datetime import date
from types import SimpleNamespace

import pytest
import uvicorn
from playwright.async_api import Error as PlaywrightError

from sandbox.portal.app import create_app as portal_app
from sandbox.register.app import create_app as register_app
from sandbox.register.db import connect
from tests.verify.util import FakeProbes
from worker.console.service import RunService
from worker.contracts import Approval, Element, Fact, FactType, Observation, Principal
from worker.llm.fake import FakeProvider
from worker.llm.provider import ProviderResponse
from worker.policy.approvals import decide_approval
from worker.runtime.loop import WorkerLoop
from worker.runtime.state import RuntimeState, load_state
from worker.store import Store
from worker.tools.browser import BrowserSession
from worker.tools.files import WorkspaceFiles
from worker.verify.probes import CsvRows, Probes


@pytest.mark.asyncio
async def test_repeating_an_unchanged_fill_is_not_progress(tmp_path):
    observation = Observation(observation_id="o1", run_id="r1", step=1,
                              url="http://register/invoices/new", title="New invoice",
                              text="", elements=[Element(ref="e3", role="textbox",
                                                         name="Invoice number", value="LS-1042")],
                              content_hash="hash")

    async def no_fill(ref, value):
        raise AssertionError("An unchanged field must not be filled again")

    async def snapshot():
        return observation

    browser = SimpleNamespace(current=observation, fill=no_fill, snapshot=snapshot)
    state = RuntimeState("r1", ["Register LS-1042"], set())
    state.facts["invoice_number"] = Fact(
        key="invoice_number", value="LS-1042", normalized="LS-1042",
        type=FactType.text, observation_id="o1", url=observation.url,
        doc_id="ls-1042", revision="1", field_locator="Invoice number")
    worker = WorkerLoop(store=None, provider=None, browser=browser, probes=None,
                        workspace=None, portal_url="", register_url="")
    result = await worker._dispatch(state, "fill_form", {"fields": [
        {"label": "Invoice number", "fact": "invoice_number"}]})
    assert not result["ok"]
    assert not result["progress"]


@pytest.mark.asyncio
async def test_browser_driver_error_is_a_tool_failure_not_a_crashed_run(tmp_path):
    class PolicyProbes(FakeProbes):
        async def register_policy(self):
            return {"version": 1, "threshold": "100000.00"}

    async def broken_navigate(url):
        raise PlaywrightError("target closed")

    store = Store(tmp_path / "worker.db")
    principal = Principal(user_id="ravi", email="ravi@example.com",
                          display_name="Ravi", role="operator")
    store.create_run("r1", "Register latest invoice", principal, "fake")
    browser = SimpleNamespace(page=SimpleNamespace(url="about:blank"), current=None,
                              navigate=broken_navigate)
    worker = WorkerLoop(store=store, provider=FakeProvider([
        {"tool": "open_page", "arguments": {"app": "portal", "page": "invoices"}},
        {"tool": "ask_user", "arguments": {"question": "The page is unavailable. Retry?"}},
    ]), browser=browser, probes=PolicyProbes(), workspace=None,
        portal_url="http://portal", register_url="http://register")
    await worker.run("r1")
    assert store.get_run("r1").status == "awaiting_input"
    assert any(event.type == "step" and not event.data["ok"]
               for event in store.events("r1"))


@pytest.mark.asyncio
async def test_navigation_adds_observation_before_next_model_call(tmp_path):
    class MultiProvider(FakeProvider):
        first = True

        async def complete(self, *, messages, tools, max_tokens, run_id):
            if self.first:
                self.first = False
                return ProviderResponse(None, [
                    {"name": "open_page", "arguments": {
                        "app": "portal", "page": "invoice", "id": "ls-1042"}},
                    {"name": "record_facts", "arguments": {
                        "labels": ["Invoice number"], "observation_id": "stale"}},
                ], "fake", None)
            return await super().complete(messages=messages, tools=tools,
                                          max_tokens=max_tokens, run_id=run_id)

    portal_url, portal_server, portal_task = await _serve(portal_app(
        tmp_path / "portal.db", reference_date=date(2026, 10, 3), probe_key="probe-demo"))
    register_url, register_server, register_task = await _serve(register_app(
        tmp_path / "register.db", reference_date=date(2026, 10, 3)))
    principal = Principal(user_id="ravi", email="ravi@example.com",
                          display_name="Ravi", role="operator")
    store = Store(tmp_path / "worker.db")
    store.create_run("r1", "Register latest invoice from Larkspur Supplies", principal, "fake")
    browser = await BrowserSession.start("r1", principal, portal_url=portal_url,
                                         register_url=register_url)
    cookies = await browser.context.cookies(register_url)
    session = next(item["value"] for item in cookies if item["name"] == "reg_session")
    probes = Probes(portal_url=portal_url, register_url=register_url,
                    probe_key="probe-demo", register_session=session,
                    workspace=tmp_path / "workspace")
    try:
        worker = WorkerLoop(store=store, provider=MultiProvider([
            {"tool": "record_facts", "arguments": {"labels": ["Invoice number"]}},
        ]), browser=browser, probes=probes, workspace=None,
            portal_url=portal_url, register_url=register_url)
        await worker.run("r1", max_steps=2)
        assert any(event.type == "fact" for event in store.events("r1"))
        assert not any(event.type == "step" and event.data["tool"] == "record_facts"
                       and event.data["args"].get("observation_id") == "stale"
                       for event in store.events("r1"))
        state = load_state(store.path, "r1")
        repeated = await worker._dispatch(state, "open_page",
                                          {"app": "portal", "page": "invoice", "id": "ls-1042"})
        assert not repeated["ok"]
    finally:
        await probes.close()
        await browser.close()
        portal_server.should_exit = True
        register_server.should_exit = True
        await portal_task
        await register_task


@pytest.mark.asyncio
async def test_finish_without_contract_is_not_completed(tmp_path):
    store = Store(tmp_path / "worker.db")
    principal = Principal(user_id="ravi", email="ravi@example.com",
                          display_name="Ravi", role="operator")
    store.create_run("r1", "Register latest invoice from Larkspur Supplies", principal, "fake")
    loop = WorkerLoop(store=store, provider=FakeProvider([{"tool": "finish",
                                                           "arguments": {"summary": "Done"}}]),
                      browser=None, probes=None, workspace=None,
                      portal_url="http://127.0.0.1:8101", register_url="http://127.0.0.1:8102")
    await loop.run("r1")
    assert store.get_run("r1").status != "completed"
    assert not any(event.type == "verification" and event.data.get("passed")
                   for event in store.events("r1"))


@pytest.mark.asyncio
async def test_unsupported_goal_ends_explicitly(tmp_path):
    store = Store(tmp_path / "worker.db")
    principal = Principal(user_id="ravi", email="ravi@example.com",
                          display_name="Ravi", role="operator")
    store.create_run("r1", "Pay all suppliers", principal, "fake")
    worker = WorkerLoop(store=store, provider=FakeProvider([
        {"tool": "commit_goal", "arguments": {"contract": {"goal_type": "make_payment"}}},
    ]), browser=None, probes=None, workspace=None,
        portal_url="http://127.0.0.1:8101", register_url="http://127.0.0.1:8102")
    await worker.run("r1")
    assert store.get_run("r1").status == "unsupported"


@pytest.mark.asyncio
async def test_model_can_mark_payment_request_unsupported(tmp_path):
    store = Store(tmp_path / "worker.db")
    principal = Principal(user_id="ravi", email="ravi@example.com",
                          display_name="Ravi", role="operator")
    store.create_run("r1", "Pay all suppliers today", principal, "fake")
    worker = WorkerLoop(store=store, provider=FakeProvider([
        {"tool": "unsupported", "arguments": {"reason": "Payments are not supported."}},
    ]), browser=None, probes=None, workspace=None,
        portal_url="http://portal", register_url="http://register")
    await worker.run("r1")
    assert store.get_run("r1").status == "unsupported"
    statuses = [event for event in store.events("r1") if event.type == "run_status"]
    assert "Payments" in statuses[-1].data["reason"]


@pytest.mark.asyncio
async def test_ambiguous_supplier_pauses_and_answer_allows_goal_commit(tmp_path):
    class ProbesWithPolicy(FakeProbes):
        async def register_policy(self):
            return {"version": 1, "threshold": "100000.00"}

    store = Store(tmp_path / "worker.db")
    principal = Principal(user_id="ravi", email="ravi@example.com",
                          display_name="Ravi", role="operator")
    store.create_run("r1", "Register latest invoice from Larkspur", principal, "fake")
    provider = FakeProvider([
        {"tool": "commit_goal", "arguments": {"contract": {"goal_type": "register_invoice",
            "supplier": "Larkspur", "selector": "latest"}}},
        {"tool": "commit_goal", "arguments": {"contract": {"goal_type": "register_invoice",
            "supplier": "Larkspur Supplies", "selector": "latest"}}},
    ])
    worker = WorkerLoop(store=store, provider=provider, browser=None,
                        probes=ProbesWithPolicy(), workspace=None,
                        portal_url="http://127.0.0.1:8101", register_url="http://127.0.0.1:8102")
    await worker.run("r1")
    assert store.get_run("r1").status == "awaiting_input"
    assert any(event.type == "question" and "Larkspur Supplies" in event.data["candidates"]
               for event in store.events("r1"))
    await worker.run("r1", answer="Larkspur Supplies")
    assert any(event.type == "contract" for event in store.events("r1"))


@pytest.mark.asyncio
async def test_existing_invoice_finishes_without_write(tmp_path):
    class ExistingProbes(FakeProbes):
        async def register_policy(self):
            return {"version": 1, "threshold": "100000.00"}

    probes = ExistingProbes()
    probes.registered = [{**probes.documents[1], "id": 7, "version": 1}]
    store = Store(tmp_path / "worker.db")
    principal = Principal(user_id="ravi", email="ravi@example.com",
                          display_name="Ravi", role="operator")
    store.create_run("r1", "Check or register LS-1042 from Larkspur Supplies", principal, "fake")
    worker = WorkerLoop(store=store, provider=FakeProvider([
        {"tool": "commit_goal", "arguments": {"contract": {
            "goal_type": "check_or_register_invoice", "supplier": "Larkspur Supplies",
            "selector": "invoice_number", "invoice_number": "LS-1042"}}},
        {"tool": "finish", "arguments": {"summary": "Done"}},
    ]), browser=None, probes=probes, workspace=None,
        portal_url="http://127.0.0.1:8101", register_url="http://127.0.0.1:8102")
    await worker.run("r1")
    assert store.get_run("r1").status == "completed"
    assert not store.pending_for_run("r1")


@pytest.mark.asyncio
async def test_export_uses_probe_rows_and_verifies_exact_csv(tmp_path):
    class ExportProbes(FakeProbes):
        async def register_policy(self):
            return {"version": 1, "threshold": "100000.00"}

        async def workspace_csv(self, path):
            with (tmp_path / "workspace" / path).open(newline="") as stream:
                reader = csv.DictReader(stream)
                return CsvRows(list(reader), reader.fieldnames or [])

    probes = ExportProbes()
    probes.registered = [dict(probes.documents[0]), dict(probes.documents[1])]
    store = Store(tmp_path / "worker.db")
    principal = Principal(user_id="ravi", email="ravi@example.com",
                          display_name="Ravi", role="operator")
    store.create_run("r1", "Export invoices due before 2026-12-01", principal, "fake")
    worker = WorkerLoop(store=store, provider=FakeProvider([
        {"tool": "commit_goal", "arguments": {"contract": {
            "goal_type": "export_invoices", "selector": "filter", "due_before": "2026-12-01"}}},
        {"tool": "files_list", "arguments": {"path": "exports"}},
        {"tool": "files_write", "arguments": {"name": "due.csv",
            "probe_query": {"due_before": "2026-12-01"}}},
        {"tool": "finish", "arguments": {"summary": "Done"}},
    ]), browser=None, probes=probes, workspace=WorkspaceFiles(tmp_path / "workspace"),
        portal_url="http://127.0.0.1:8101", register_url="http://127.0.0.1:8102")
    await worker.run("r1")
    assert store.get_run("r1").status == "completed"
    assert (tmp_path / "workspace" / "exports" / "due.csv").is_file()
    assert any(event.type == "step" and event.data["tool"] == "files_list"
               and not event.data["ok"] for event in store.events("r1"))


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


def _intake_script(portal_url, register_url, *, supplier="Larkspur Supplies",
                   number="LS-1042", fault=None):
    approval_case = fault in {"approval", "reject"}
    doc = number.lower()
    proposal = {"requested_action": "register an invoice", "goal_type": "register_invoice",
                "supplier": supplier,
                "selector": "invoice_number" if approval_case else "latest"}
    if approval_case:
        proposal["invoice_number"] = number
    script = [
        {"tool": "commit_goal", "arguments": {"contract": proposal}},
        {"tool": "open_page", "arguments": {"app": "portal", "page": "invoices"}},
        {"tool": "browser_click", "target": number},
        {"tool": "record_facts", "arguments": {
            "labels": ["Invoice number", "Amount", "Due date", "Currency"]}},
    ]
    amount, due = ("Total", "Payment due") if fault == "layout_b" else ("Amount", "Due date")
    write_steps = [
        {"tool": "open_page", "arguments": {"app": "register", "page": "new_invoice"}},
        {"tool": "fill_form", "arguments": {"fields": [
            {"label": "Supplier", "fact": "goal.supplier"},
            {"label": "Invoice number", "fact": f"{doc}.invoice_number"},
            {"label": amount, "fact": f"{doc}.amount"},
            {"label": due, "fact": f"{doc}.due_date"},
            {"label": "Currency", "fact": f"{doc}.currency"},
            {"label": "Source document", "fact": f"{doc}.document_id"},
        ]}},
        {"tool": "submit_form"},
    ]
    script += write_steps
    if fault == "fail_next_save":
        script += write_steps
    if approval_case:
        script += [{"tool": "submit_form"}]
    script += [{"tool": "finish", "arguments": {"summary": "Done"}}]
    return script


@pytest.mark.parametrize(("fault", "user_id", "expected_status"), [
    (None, "ravi", "completed"),
    ("fail_next_save", "ravi", "completed"),
    ("commit_then_timeout", "ravi", "completed"),
    (None, "meera", "blocked"),
    ("approval", "ravi", "completed"),
    ("reject", "ravi", "blocked"),
    ("layout_b", "ravi", "completed"),
    ("corrupt_next_save", "ravi", "failed"),
])
@pytest.mark.asyncio
async def test_fake_model_drives_real_browser_and_verifies_invoice(tmp_path, fault, user_id, expected_status):
    portal_url, portal_server, portal_task = await _serve(portal_app(
        tmp_path / "portal.db", reference_date=date(2026, 10, 3), probe_key="probe-demo"))
    register_url, register_server, register_task = await _serve(register_app(
        tmp_path / "register.db", reference_date=date(2026, 10, 3)))
    if fault in {"fail_next_save", "commit_then_timeout", "layout_b", "corrupt_next_save"}:
        with connect(tmp_path / "register.db") as db:
            if fault == "commit_then_timeout":
                db.execute("UPDATE faults SET commit_then_timeout=1 WHERE id=1")
            elif fault == "layout_b":
                db.execute("UPDATE faults SET layout_variant='b' WHERE id=1")
            elif fault == "corrupt_next_save":
                db.execute("UPDATE faults SET corrupt_next_save=1 WHERE id=1")
            else:
                db.execute("UPDATE faults SET fail_next_save=1 WHERE id=1")
    principal = Principal(user_id=user_id, email=f"{user_id}@example.com",
                          display_name=user_id.title(), role="operator")
    browser = await BrowserSession.start("r1", principal, portal_url=portal_url,
                                         register_url=register_url)
    cookies = await browser.context.cookies(register_url)
    session = next(item["value"] for item in cookies if item["name"] == "reg_session")
    probes = Probes(portal_url=portal_url, register_url=register_url, probe_key="probe-demo",
                    register_session=session, workspace=tmp_path / "workspace")
    store = Store(tmp_path / "worker.db")
    approval_case = fault in {"approval", "reject"}
    supplier = "Brightfen Paper" if approval_case else "Larkspur Supplies"
    number = "BF-2292" if approval_case else "LS-1042"
    request = (f"Register invoice {number} from {supplier}" if approval_case
               else "Register the latest invoice from Larkspur Supplies")
    store.create_run("r1", request, principal, "fake")
    script = _intake_script(portal_url, register_url, supplier=supplier,
                            number=number, fault=fault)
    try:
        worker = WorkerLoop(store=store, provider=FakeProvider(script), browser=browser,
                            probes=probes, workspace=WorkspaceFiles(tmp_path / "workspace"),
                            portal_url=portal_url, register_url=register_url)
        await worker.run("r1")
        if approval_case:
            assert store.get_run("r1").status == "awaiting_approval"
            approval = store.approvals("r1")[0]
            approved = decide_approval(Approval.model_validate(approval),
                                       "reject" if fault == "reject" else "approve",
                                       "ravi@example.com")
            store.save_approval(approved.approval_id, "r1", approved.model_dump(mode="json"))
            await worker.run("r1")
        assert store.get_run("r1").status == expected_status, [
            (event.type, event.data) for event in store.events("r1")]
        rows = await probes.register_invoices(supplier_id=(
            "brightfen-paper" if approval_case else "larkspur-supplies"))
        assert [row["invoice_number"] for row in rows].count(number) == (
            1 if expected_status in {"completed", "failed"} else 0)
        assert any(event.type == "verification" and event.data["passed"]
                   for event in store.events("r1")) == (expected_status == "completed")
        for event in store.events("r1"):
            if event.type == "contract":
                assert event.data["action"] in {"committed", "revised", "rejected"}
            elif event.type in {"fact", "gate"}:
                assert isinstance(event.data["step"], int)
            elif event.type == "pending":
                assert {"mutation_id", "run_id", "form_token", "target_key",
                        "intended_values", "state"} <= set(event.data)
                assert event.data["form_token"] == "•••"
            elif event.type == "error":
                assert isinstance(event.data["retryable"], bool)
        assert all("step" not in fact for fact in RunService(store).detail("r1", principal)["facts"])
        screenshots = [event.data["screenshot"] for event in store.events("r1")
                       if event.type == "step" and event.data.get("screenshot")]
        assert screenshots
        assert (tmp_path / "artifacts" / "r1" / screenshots[-1]).is_file()
    finally:
        await probes.close()
        await browser.close()
        portal_server.should_exit = True
        register_server.should_exit = True
        await portal_task
        await register_task


@pytest.mark.asyncio
async def test_restart_after_dispatch_reconciles_exactly_one_invoice(tmp_path):
    portal_url, portal_server, portal_task = await _serve(portal_app(
        tmp_path / "portal.db", reference_date=date(2026, 10, 3), probe_key="probe-demo"))
    register_url, register_server, register_task = await _serve(register_app(
        tmp_path / "register.db", reference_date=date(2026, 10, 3)))
    with connect(tmp_path / "register.db") as db:
        db.execute("UPDATE faults SET commit_then_timeout=1 WHERE id=1")
    principal = Principal(user_id="ravi", email="ravi@example.com",
                          display_name="Ravi", role="operator")
    store = Store(tmp_path / "worker.db")
    store.create_run("r1", "Register latest invoice from Larkspur Supplies", principal, "fake")
    workspace = WorkspaceFiles(tmp_path / "workspace")

    async def make_worker(script):
        browser = await BrowserSession.start("r1", principal, portal_url=portal_url,
                                             register_url=register_url)
        cookies = await browser.context.cookies(register_url)
        session = next(item["value"] for item in cookies if item["name"] == "reg_session")
        probes = Probes(portal_url=portal_url, register_url=register_url,
                        probe_key="probe-demo", register_session=session,
                        workspace=tmp_path / "workspace")
        worker = WorkerLoop(store=store, provider=FakeProvider(script), browser=browser,
                            probes=probes, workspace=workspace,
                            portal_url=portal_url, register_url=register_url)
        return worker, browser, probes

    first, browser, probes = await make_worker(_intake_script(portal_url, register_url))
    task = asyncio.create_task(first.run("r1"))
    try:
        for _ in range(300):
            await asyncio.sleep(0.02)
            with connect(tmp_path / "register.db") as db:
                saved = db.execute("SELECT COUNT(*) FROM invoices WHERE invoice_number='LS-1042'").fetchone()[0]
            if saved and any(item.state == "dispatching" for item in store.pending_for_run("r1")):
                break
        assert saved == 1
        assert store.pending_for_run("r1")[0].state == "dispatching"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await probes.close()
        await browser.close()
        store.update_run("r1", status="interrupted")
        resumed, new_browser, new_probes = await make_worker([
            {"tool": "finish", "arguments": {"summary": "Done"}},
        ])
        try:
            await resumed.run("r1")
            assert store.get_run("r1").status == "completed"
            assert store.pending_for_run("r1")[0].state == "committed"
            rows = await new_probes.register_invoices(supplier_id="larkspur-supplies")
            assert [row["invoice_number"] for row in rows].count("LS-1042") == 1
        finally:
            await new_probes.close()
            await new_browser.close()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        portal_server.should_exit = True
        register_server.should_exit = True
        await portal_task
        await register_task


@pytest.mark.asyncio
async def test_contact_update_requires_approval_and_verifies_source(tmp_path):
    portal_url, portal_server, portal_task = await _serve(portal_app(
        tmp_path / "portal.db", reference_date=date(2026, 10, 3), probe_key="probe-demo"))
    register_url, register_server, register_task = await _serve(register_app(
        tmp_path / "register.db", reference_date=date(2026, 10, 3)))
    principal = Principal(user_id="ravi", email="ravi@example.com",
                          display_name="Ravi", role="operator")
    browser = await BrowserSession.start("r1", principal, portal_url=portal_url,
                                         register_url=register_url)
    cookies = await browser.context.cookies(register_url)
    session = next(item["value"] for item in cookies if item["name"] == "reg_session")
    store = Store(tmp_path / "worker.db")
    store.create_run("r1", "Update Larkspur Supplies contact from their message", principal, "fake")
    probes = Probes(portal_url=portal_url, register_url=register_url,
                    probe_key="probe-demo", register_session=session,
                    workspace=tmp_path / "workspace", store=store)
    script = [
        {"tool": "commit_goal", "arguments": {"contract": {
            "requested_action": "update a supplier contact",
            "goal_type": "update_supplier_contact", "supplier": "Larkspur Supplies",
            "selector": "message"}}},
        {"tool": "open_page", "arguments": {"app": "portal", "page": "message",
                                            "id": "msg-larkspur"}},
        {"tool": "record_facts", "arguments": {
            "labels": ["Contact name", "Contact email", "Remittance email"]}},
        {"tool": "open_page", "arguments": {"app": "register", "page": "supplier_edit",
                                            "id": "larkspur-supplies"}},
        {"tool": "fill_form", "arguments": {"fields": [
            {"label": label, "fact": f"msg-larkspur.{key}"} for key, label in [
                ("contact_name", "Contact name"), ("contact_email", "Contact email"),
                ("remittance_email", "Remittance email")]]}},
        {"tool": "submit_form"},
        {"tool": "submit_form"},
        {"tool": "finish", "arguments": {"summary": "Done"}},
    ]
    worker = WorkerLoop(store=store, provider=FakeProvider(script), browser=browser,
                        probes=probes, workspace=WorkspaceFiles(tmp_path / "workspace"),
                        portal_url=portal_url, register_url=register_url)
    try:
        await worker.run("r1")
        assert store.get_run("r1").status == "awaiting_approval"
        approval = Approval.model_validate(store.approvals("r1")[0])
        approved = decide_approval(approval, "approve", "ravi@example.com")
        store.save_approval(approved.approval_id, "r1", approved.model_dump(mode="json"))
        await worker.run("r1")
        assert store.get_run("r1").status == "completed", [
            (event.type, event.data.get("summary")) for event in store.events("r1")]
        supplier = await probes.register_supplier("larkspur-supplies")
        assert supplier["contact_email"] == "nina@larkspur.example.com"
    finally:
        await probes.close()
        await browser.close()
        portal_server.should_exit = True
        register_server.should_exit = True
        await portal_task
        await register_task


@pytest.mark.parametrize("layout", ["a", "b"])
@pytest.mark.asyncio
async def test_task_level_tools_complete_intake_on_either_form_layout(tmp_path, layout):
    """open_page/record_facts/fill_form/submit_form, with labels resolved by code, no refs."""
    portal_url, portal_server, portal_task = await _serve(portal_app(
        tmp_path / "portal.db", reference_date=date(2026, 10, 3), probe_key="probe-demo"))
    register_url, register_server, register_task = await _serve(register_app(
        tmp_path / "register.db", reference_date=date(2026, 10, 3)))
    if layout == "b":
        with connect(tmp_path / "register.db") as db:
            db.execute("UPDATE faults SET layout_variant='b' WHERE id=1")
    principal = Principal(user_id="ravi", email="ravi@example.com", display_name="Ravi",
                          role="operator")
    browser = await BrowserSession.start("r1", principal, portal_url=portal_url,
                                         register_url=register_url)
    cookies = await browser.context.cookies(register_url)
    session = next(item["value"] for item in cookies if item["name"] == "reg_session")
    probes = Probes(portal_url=portal_url, register_url=register_url, probe_key="probe-demo",
                    register_session=session, workspace=tmp_path / "workspace")
    store = Store(tmp_path / "worker.db")
    store.create_run("r1", "Register the latest invoice from Larkspur Supplies", principal, "fake")
    amount, due = ("Total", "Payment due") if layout == "b" else ("Amount", "Due date")
    script = [
        {"tool": "commit_goal", "arguments": {"contract": {
            "goal_type": "register_invoice", "supplier": "Larkspur Supplies", "selector": "latest"}}},
        {"tool": "open_page", "arguments": {"app": "portal", "page": "invoice", "id": "ls-1042"}},
        {"tool": "record_facts", "arguments": {
            "labels": ["Invoice number", "Amount", "Due date", "Currency"]}},
        {"tool": "open_page", "arguments": {"app": "register", "page": "new_invoice"}},
        {"tool": "fill_form", "arguments": {"fields": [
            {"label": "Supplier", "fact": "goal.supplier"},
            {"label": "Invoice number", "fact": "ls-1042.invoice_number"},
            {"label": amount, "fact": "ls-1042.amount"},
            {"label": due, "fact": "ls-1042.due_date"},
            {"label": "Currency", "fact": "ls-1042.currency"},
            {"label": "Source document", "fact": "ls-1042.document_id"},
        ]}},
        {"tool": "submit_form"},
        {"tool": "finish", "arguments": {"summary": "Done"}},
    ]
    try:
        worker = WorkerLoop(store=store, provider=FakeProvider(script), browser=browser,
                            probes=probes, workspace=WorkspaceFiles(tmp_path / "workspace"),
                            portal_url=portal_url, register_url=register_url)
        await worker.run("r1")
        steps = [(event.data["tool"], event.data["ok"], event.data["summary"])
                 for event in store.events("r1") if event.type == "step"]
        assert store.get_run("r1").status == "completed", steps
        with connect(tmp_path / "register.db") as db:
            assert db.execute("SELECT COUNT(*) FROM invoices WHERE invoice_number='LS-1042'"
                              ).fetchone()[0] == 1
        assert len(steps) == 7
        plans = [event.data for event in store.events("r1") if event.type == "plan"]
        assert plans and all(step["status"] == "done" for step in plans[-1]["steps"])
        assert all(isinstance(step, dict) for plan in plans for step in plan["steps"])
        summary = next(event.data["summary"] for event in store.events("r1")
                       if event.type == "verification")
        assert summary.startswith("Saved invoice from Larkspur Supplies to the register: LS-1042 (")
    finally:
        await probes.close()
        await browser.close()
        portal_server.should_exit = True
        register_server.should_exit = True
        await portal_task
        await register_task


@pytest.mark.asyncio
async def test_unrepairable_failed_verification_ends_failed_not_blocked(tmp_path):
    class PolicyProbes(FakeProbes):
        async def register_policy(self):
            return {"version": 1, "threshold": "100000.00"}

    store = Store(tmp_path / "worker.db")
    principal = Principal(user_id="ravi", email="ravi@example.com", display_name="Ravi",
                          role="operator")
    store.create_run("r1", "Register the latest invoice from Larkspur Supplies", principal, "fake")
    script = [{"tool": "commit_goal", "arguments": {"contract": {
        "requested_action": "register the latest invoice", "goal_type": "register_invoice",
        "supplier": "Larkspur Supplies", "selector": "latest"}}},
              {"tool": "finish", "arguments": {"summary": "Done"}}]
    script += [{"tool": "update_plan", "arguments": {"steps": ["stuck"]}}] * 8
    worker = WorkerLoop(store=store, provider=FakeProvider(script), browser=None,
                        probes=PolicyProbes(), workspace=None,
                        portal_url="http://127.0.0.1:8101", register_url="http://127.0.0.1:8102")
    await worker.run("r1")
    assert store.get_run("r1").status == "failed"


@pytest.mark.asyncio
async def test_revise_goal_accepts_the_restated_action(tmp_path):
    class PolicyProbes(FakeProbes):
        async def register_policy(self):
            return {"version": 1, "threshold": "100000.00"}

    store = Store(tmp_path / "worker.db")
    principal = Principal(user_id="ravi", email="ravi@example.com", display_name="Ravi",
                          role="operator")
    store.create_run("r1", "Register the latest invoice from Larkspur Supplies", principal, "fake")
    goal = {"requested_action": "register the latest invoice", "goal_type": "register_invoice",
            "supplier": "Larkspur Supplies", "selector": "latest", "extra_criteria": [{}]}
    worker = WorkerLoop(store=store, provider=FakeProvider([
        {"tool": "commit_goal", "arguments": {"contract": goal}},
        {"tool": "finish", "arguments": {"summary": "Done"}},
        {"tool": "revise_goal", "arguments": {"contract": goal}},
        {"tool": "ask_user", "arguments": {"question": "?"}},
    ]), browser=None, probes=PolicyProbes(), workspace=None,
        portal_url="http://127.0.0.1:8101", register_url="http://127.0.0.1:8102")
    await worker.run("r1")
    revise = [event for event in store.events("r1")
              if event.type == "step" and event.data["tool"] == "revise_goal"]
    assert revise and "extra_forbidden" not in revise[0].data["summary"]


@pytest.mark.asyncio
async def test_submit_form_after_an_approval_pause_saves_the_approved_values(tmp_path):
    portal_url, portal_server, portal_task = await _serve(portal_app(
        tmp_path / "portal.db", reference_date=date(2026, 10, 3), probe_key="probe-demo"))
    register_url, register_server, register_task = await _serve(register_app(
        tmp_path / "register.db", reference_date=date(2026, 10, 3)))
    principal = Principal(user_id="ravi", email="ravi@example.com", display_name="Ravi",
                          role="operator")
    browser = await BrowserSession.start("r1", principal, portal_url=portal_url,
                                         register_url=register_url)
    cookies = await browser.context.cookies(register_url)
    session = next(item["value"] for item in cookies if item["name"] == "reg_session")
    probes = Probes(portal_url=portal_url, register_url=register_url, probe_key="probe-demo",
                    register_session=session, workspace=tmp_path / "workspace")
    store = Store(tmp_path / "worker.db")
    store.create_run("r1", "Register invoice BF-2292 from Brightfen Paper", principal, "fake")
    script = [
        {"tool": "commit_goal", "arguments": {"contract": {
            "requested_action": "register an invoice", "goal_type": "register_invoice",
            "supplier": "Brightfen Paper", "selector": "invoice_number",
            "invoice_number": "BF-2292"}}},
        {"tool": "open_page", "arguments": {"app": "portal", "page": "invoice", "id": "bf-2292"}},
        {"tool": "record_facts", "arguments": {
            "labels": ["Invoice number", "Amount", "Due date", "Currency"]}},
        {"tool": "open_page", "arguments": {"app": "register", "page": "new_invoice"}},
        {"tool": "fill_form", "arguments": {"fields": [
            {"label": "Supplier", "fact": "goal.supplier"},
            {"label": "Invoice number", "fact": "bf-2292.invoice_number"},
            {"label": "Amount", "fact": "bf-2292.amount"},
            {"label": "Due date", "fact": "bf-2292.due_date"},
            {"label": "Currency", "fact": "bf-2292.currency"},
            {"label": "Source document", "fact": "bf-2292.document_id"},
        ]}},
        {"tool": "submit_form"},
        {"tool": "submit_form"},
        {"tool": "finish", "arguments": {"summary": "Done"}},
    ]
    try:
        worker = WorkerLoop(store=store, provider=FakeProvider(script), browser=browser,
                            probes=probes, workspace=WorkspaceFiles(tmp_path / "workspace"),
                            portal_url=portal_url, register_url=register_url)
        await worker.run("r1")
        assert store.get_run("r1").status == "awaiting_approval"
        approved = decide_approval(Approval.model_validate(store.approvals("r1")[0]), "approve",
                                   "ravi@example.com")
        store.save_approval(approved.approval_id, "r1", approved.model_dump(mode="json"))
        await worker.run("r1")
        steps = [(event.data["tool"], event.data["summary"]) for event in store.events("r1")
                 if event.type == "step"]
        assert store.get_run("r1").status == "completed", steps
        with connect(tmp_path / "register.db") as db:
            assert db.execute("SELECT COUNT(*) FROM invoices WHERE invoice_number='BF-2292'"
                              ).fetchone()[0] == 1
    finally:
        await probes.close()
        await browser.close()
        portal_server.should_exit = True
        register_server.should_exit = True
        await portal_task
        await register_task


@pytest.mark.asyncio
async def test_error_pages_and_formless_pages_give_actionable_feedback(tmp_path):
    portal_url, portal_server, portal_task = await _serve(portal_app(
        tmp_path / "portal.db", reference_date=date(2026, 10, 3), probe_key="probe-demo"))
    register_url, register_server, register_task = await _serve(register_app(
        tmp_path / "register.db", reference_date=date(2026, 10, 3)))
    principal = Principal(user_id="meera", email="meera@example.com", display_name="Meera",
                          role="operator")
    browser = await BrowserSession.start("r1", principal, portal_url=portal_url,
                                         register_url=register_url)
    cookies = await browser.context.cookies(register_url)
    session = next(item["value"] for item in cookies if item["name"] == "reg_session")
    probes = Probes(portal_url=portal_url, register_url=register_url, probe_key="probe-demo",
                    register_session=session, workspace=tmp_path / "workspace")
    store = Store(tmp_path / "worker.db")
    store.create_run("r1", "Kestrova Components sent new contact details", principal, "fake")
    try:
        worker = WorkerLoop(store=store, provider=FakeProvider([
            {"tool": "open_page", "arguments": {"app": "register", "page": "supplier_edit",
                                                "id": "Kestrova Components"}},
            {"tool": "open_page", "arguments": {"app": "portal", "page": "invoice", "id": "kc-702"}},
            {"tool": "fill_form", "arguments": {"fields": [{"label": "Amount", "text": "1"}]}},
            {"tool": "ask_user", "arguments": {"question": "?"}},
        ]), browser=browser, probes=probes, workspace=None,
            portal_url=portal_url, register_url=register_url)
        await worker.run("r1")
        steps = [event.data for event in store.events("r1") if event.type == "step"]
        assert not steps[0]["ok"] and "no such page" in steps[0]["summary"]
        assert not steps[2]["ok"] and "has no form" in steps[2]["summary"]
    finally:
        await probes.close()
        await browser.close()
        portal_server.should_exit = True
        register_server.should_exit = True
        await portal_task
        await register_task


@pytest.mark.asyncio
async def test_memory_suggests_a_users_earlier_choice_but_still_asks(tmp_path):
    class ProbesWithPolicy(FakeProbes):
        async def register_policy(self):
            return {"version": 1, "threshold": "100000.00"}

    store = Store(tmp_path / "worker.db")
    ravi = Principal(user_id="ravi", email="ravi@example.com", display_name="Ravi", role="operator")
    asha = Principal(user_id="asha", email="asha@example.com", display_name="Asha", role="admin")
    ambiguous = {"tool": "commit_goal", "arguments": {"contract": {
        "requested_action": "register latest", "goal_type": "register_invoice",
        "supplier": "Larkspur", "selector": "latest"}}}

    def worker(script):
        return WorkerLoop(store=store, provider=FakeProvider(script), browser=None,
                          probes=ProbesWithPolicy(), workspace=None,
                          portal_url="http://127.0.0.1:8101", register_url="http://127.0.0.1:8102")

    def last_question(run_id):
        return [event.data for event in store.events(run_id) if event.type == "question"][-1]

    store.create_run("r1", "Register the latest invoice from Larkspur", ravi, "fake")
    first = worker([ambiguous, {"tool": "ask_user", "arguments": {"question": "?"}}])
    await first.run("r1")
    assert "Which one did you mean" in last_question("r1")["text"]
    assert "suggested" not in last_question("r1")
    await first.run("r1", answer="Larkspur Supplies please")

    store.create_run("r2", "Log the newest Larkspur bill", ravi, "fake")
    await worker([ambiguous]).run("r2")
    assert store.get_run("r2").status == "awaiting_input"
    assert last_question("r2")["suggested"] == "Larkspur Supplies"
    assert "Last time you chose Larkspur Supplies" in last_question("r2")["text"]

    store.create_run("r3", "Log the newest Larkspur bill", asha, "fake")
    await worker([ambiguous]).run("r3")
    assert "suggested" not in last_question("r3")


@pytest.mark.asyncio
async def test_failed_save_and_empty_form_explain_what_to_do(tmp_path):
    portal_url, portal_server, portal_task = await _serve(portal_app(
        tmp_path / "portal.db", reference_date=date(2026, 10, 3), probe_key="probe-demo"))
    register_url, register_server, register_task = await _serve(register_app(
        tmp_path / "register.db", reference_date=date(2026, 10, 3)))
    with connect(tmp_path / "register.db") as db:
        db.execute("UPDATE faults SET fail_next_save=1 WHERE id=1")
    principal = Principal(user_id="ravi", email="ravi@example.com", display_name="Ravi",
                          role="operator")
    browser = await BrowserSession.start("r1", principal, portal_url=portal_url,
                                         register_url=register_url)
    cookies = await browser.context.cookies(register_url)
    session = next(item["value"] for item in cookies if item["name"] == "reg_session")
    probes = Probes(portal_url=portal_url, register_url=register_url, probe_key="probe-demo",
                    register_session=session, workspace=tmp_path / "workspace")
    store = Store(tmp_path / "worker.db")
    store.create_run("r1", "Register the latest invoice from Larkspur Supplies", principal, "fake")
    script = _intake_script(portal_url, register_url)
    submit = script.index({"tool": "submit_form"})
    # after the failed save: reopen the form and submit it without filling it
    script = script[:submit + 1] + [
        {"tool": "open_page", "arguments": {"app": "register", "page": "new_invoice"}},
        {"tool": "submit_form"},
        {"tool": "ask_user", "arguments": {"question": "?"}},
    ]
    try:
        worker = WorkerLoop(store=store, provider=FakeProvider(script), browser=browser,
                            probes=probes, workspace=WorkspaceFiles(tmp_path / "workspace"),
                            portal_url=portal_url, register_url=register_url)
        await worker.run("r1")
        submits = [event.data["summary"] for event in store.events("r1")
                   if event.type == "step" and event.data["tool"] == "submit_form"]
        assert "nothing was written" in submits[0] and "fill it with fill_form" in submits[0]
        assert "Empty fields" in submits[1] and "Amount" in submits[1]
    finally:
        await probes.close()
        await browser.close()
        portal_server.should_exit = True
        register_server.should_exit = True
        await portal_task
        await register_task
