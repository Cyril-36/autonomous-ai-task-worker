import asyncio
import socket

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from playwright.async_api import Error as PlaywrightError

from worker.contracts import NetworkAllowance
from worker.tools.browser import BrowserSession


@pytest.mark.asyncio
async def test_real_browser_blocks_js_write_probe_link_and_redirect():
    app = FastAPI()
    writes = []

    @app.get("/", response_class=HTMLResponse)
    def home():
        return '<a href="/api/secret">Probe</a><form method="post" action="/save"><input name="form_token" value="t1"><input name="amount" value="48250.00"><button>Save</button></form>'

    @app.get("/api/secret")
    def probe():
        return {"secret": True}

    @app.post("/save")
    async def save(request: Request):
        writes.append(dict(await request.form()))
        return RedirectResponse("/done", status_code=303)

    @app.get("/done")
    def done():
        return {"ok": True}

    @app.get("/redirect")
    def redirect():
        return RedirectResponse("https://example.org/offsite", status_code=302)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(10)
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        await asyncio.sleep(0.01)
    session = await BrowserSession.local_test("r1", {url})
    try:
        await session.navigate(url)
        observation = await session.snapshot()
        probe_ref = next(element.ref for element in observation.elements if element.name == "Probe")
        await session.click(probe_ref)
        assert any("/api/secret" in entry["url"] for entry in session.guard.blocked)
        assert not writes
        await session.navigate(url)
        assert await session.page.evaluate("fetch('/save', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:'form_token=t1&amount=48250.00'}).then(r=>r.ok).catch(()=>false)") is False
        assert not writes
        observation = await session.snapshot()
        save_ref = next(element.ref for element in observation.elements if element.name == "Save")
        form = await session.capture_form(save_ref)
        session.guard.arm(NetworkAllowance(run_id="r1", mutation_id="m1", method="POST",
                                           url=form["action_url"], body=form["fields"]))
        await session.click(save_ref)
        assert len(writes) == 1
        await session.navigate(url)
        observation = await session.snapshot()
        save_ref = next(element.ref for element in observation.elements if element.name == "Save")
        await session.click(save_ref)
        assert len(writes) == 1
        with pytest.raises(PlaywrightError):
            await session.navigate(f"{url}/redirect")
        assert any("example.org" in entry["url"] for entry in session.guard.blocked)
    finally:
        await session.close()
        server.should_exit = True
        await task
