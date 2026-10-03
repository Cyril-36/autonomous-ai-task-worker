"""Frozen console HTTP/SSE API; frontend assets are owned by another builder."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from worker.config import ROOT, Settings
from worker.console.auth import DemoAuth
from worker.console.service import RunService
from worker.contracts import TERMINAL_STATUSES
from worker.runtime.queue import DurableQueue
from worker.runtime.runner import LiveRunner
from worker.store import Store


def create_app(
    db_path: Path | str | None = None, *, passwords: dict[str, str] | None = None,
    engine: str | None = None, runner=None,
) -> FastAPI:
    settings = Settings.from_env()
    store = Store(db_path or settings.data_dir / "worker.db")
    auth = DemoAuth(passwords)
    selected_engine = engine or settings.engine
    live_runner = LiveRunner(store, settings) if selected_engine == "live" and runner is None else None
    queue = DurableQueue(store, runner or live_runner) if selected_engine == "live" else None
    service = RunService(store, model=settings.model if (engine or settings.engine) == "live" else "replay",
                         engine=selected_engine, queue=queue,
                         ledger=live_runner.ledger if live_runner else None)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if queue:
            await queue.start()
        yield
        if queue:
            await queue.stop()
        if live_runner:
            await live_runner.close()

    app = FastAPI(title="CentrAlign task worker console API", lifespan=lifespan)
    app.state.service = service
    app.state.queue = queue

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        code, message = exc.detail if isinstance(exc.detail, tuple) else (
            "not_found" if exc.status_code == 404 else "invalid_request", str(exc.detail)
        )
        return JSONResponse({"error": {"code": code, "message": message}},
                            status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError):
        return JSONResponse({"error": {"code": "invalid_request", "message": "Invalid request body"}},
                            status_code=422)

    async def body_object(request: Request) -> dict:
        try:
            value = await request.json()
        except ValueError as exc:
            raise HTTPException(422, detail=("invalid_request", "Invalid JSON body")) from exc
        if not isinstance(value, dict):
            raise HTTPException(422, detail=("invalid_request", "Expected a JSON object"))
        return value

    @app.get("/api/demo-users")
    def demo_users():
        return auth.users()

    @app.post("/api/session")
    async def sign_in(request: Request):
        data = await body_object(request)
        principal, token = auth.sign_in(str(data.get("email", "")), str(data.get("password", "")))
        response = JSONResponse(principal.model_dump(mode="json"))
        response.set_cookie("console_session", token, httponly=True, samesite="lax")
        return response

    @app.get("/api/me")
    def me(request: Request):
        return auth.current(request)

    @app.delete("/api/session", status_code=204)
    def sign_out(request: Request):
        auth.sign_out(request)
        response = Response(status_code=204)
        response.delete_cookie("console_session")
        return response

    @app.get("/api/examples")
    def examples(request: Request):
        auth.current(request)
        return [
            {"title": "Latest invoice", "request": "Register the latest invoice from Larkspur Supplies",
             "notes": "Find, save and verify the newest source invoice"},
            {"title": "Existing invoice", "request": "Check whether BF-2291 from Brightfen Paper is registered",
             "notes": "Avoid a duplicate"},
            {"title": "Ambiguous supplier", "request": "Enter the latest invoice from Larkspur.",
             "notes": "Ask for clarification"},
            {"title": "Export due invoices", "request": "Export invoices due before 2026-11-01",
             "notes": "Create a CSV after matching the register filter"},
        ]

    @app.get("/api/budget")
    def budget(request: Request):
        auth.current(request)
        return service.budget()

    @app.get("/api/runs")
    def runs(request: Request):
        return service.list(auth.current(request))

    @app.post("/api/runs", status_code=201)
    async def submit(request: Request):
        principal = auth.current(request)
        data = await body_object(request)
        if not isinstance(data.get("request"), str):
            raise HTTPException(422, detail=("invalid_request", "Request text is required"))
        return service.submit(principal, data["request"])

    @app.get("/api/runs/{run_id}")
    def detail(run_id: str, request: Request):
        return service.detail(run_id, auth.current(request))

    @app.get("/api/runs/{run_id}/events")
    def events(run_id: str, request: Request, after: int = 0):
        return service.events(run_id, auth.current(request), after)

    @app.get("/api/runs/{run_id}/stream")
    async def stream(run_id: str, request: Request):
        principal = auth.current(request)
        service._visible(run_id, principal)
        raw_last = request.headers.get("Last-Event-ID", "0")
        try:
            after = max(0, int(raw_last))
        except ValueError as exc:
            raise HTTPException(422, detail=("invalid_request", "Invalid Last-Event-ID")) from exc

        async def generate():
            nonlocal after
            idle = 0
            while True:
                batch = service.events(run_id, principal, after)
                for event in batch:
                    after = event.seq
                    yield (f"id: {event.seq}\nevent: {event.type}\n"
                           f"data: {event.model_dump_json()}\n\n")
                    if event.type == "run_status" and event.data.get("status") in {
                        status.value for status in TERMINAL_STATUSES
                    }:
                        yield "event: end\ndata: {}\n\n"
                        return
                run = service._visible(run_id, principal)
                if run.status in TERMINAL_STATUSES:
                    yield "event: end\ndata: {}\n\n"
                    return
                await asyncio.sleep(1)
                idle += 1
                if idle >= 15:
                    yield ": keepalive\n\n"
                    idle = 0

        return StreamingResponse(generate(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    @app.post("/api/runs/{run_id}/answer", status_code=202)
    async def answer(run_id: str, request: Request):
        principal = auth.current(request)
        data = await body_object(request)
        if not isinstance(data.get("text"), str):
            raise HTTPException(422, detail=("invalid_request", "Answer text is required"))
        service.answer(run_id, principal, data["text"])
        return {"ok": True}

    @app.post("/api/runs/{run_id}/approvals/{approval_id}")
    async def decide(run_id: str, approval_id: str, request: Request):
        principal = auth.current(request)
        data = await body_object(request)
        return service.decide(run_id, approval_id, principal, str(data.get("decision", "")),
                              str(data["note"]) if data.get("note") is not None else None)

    @app.post("/api/runs/{run_id}/cancel", status_code=202)
    def cancel(run_id: str, request: Request):
        service.cancel(run_id, auth.current(request))
        return {"ok": True}

    @app.get("/api/runs/{run_id}/artifacts/{name}")
    def artifact(run_id: str, name: str, request: Request):
        service._visible(run_id, auth.current(request))
        if Path(name).name != name or not name.endswith(".png"):
            raise HTTPException(404, detail=("not_found", "Artifact not found"))
        file = store.path.parent / "artifacts" / run_id / name
        if not file.is_file():
            raise HTTPException(404, detail=("not_found", "Artifact not found"))
        return FileResponse(file, media_type="image/png")

    @app.api_route("/api/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def unknown_api(full_path: str):
        raise HTTPException(404, detail=("not_found", "API route not found"))

    frontend = ROOT / "console" / "dist"
    if frontend.is_dir():
        @app.get("/{full_path:path}")
        def frontend_asset(full_path: str):
            target = (frontend / full_path).resolve()
            if target.is_file() and target.is_relative_to(frontend.resolve()):
                return FileResponse(target)
            return FileResponse(frontend / "index.html")

    return app


app = create_app()
