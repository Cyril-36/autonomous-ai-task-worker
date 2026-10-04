"""Own per-run browser, probes and model resources for live console runs."""

from __future__ import annotations

from worker.config import Settings, load_pricing, spending_ledger_path
from worker.contracts import TERMINAL_STATUSES
from worker.llm.ledger import Ledger
from worker.llm.provider import Provider
from worker.runtime.loop import WorkerLoop
from worker.runtime.prompts import PROMPT_HASH
from worker.tools.browser import BrowserSession
from worker.tools.files import WorkspaceFiles
from worker.trace.writer import TraceWriter
from worker.verify.probes import Probes


class LiveRunner:
    def __init__(self, store, settings: Settings):
        self.store = store
        self.settings = settings
        self.ledger = Ledger(spending_ledger_path(store.path.parent), load_pricing())
        self.sessions: dict[str, tuple[BrowserSession, Probes, Provider]] = {}

    async def __call__(self, run_id: str, answer: str | None = None) -> None:
        run = self.store.get_run(run_id)
        if run is None or run.status in TERMINAL_STATUSES:
            return
        if not self.settings.api_key:
            raise RuntimeError("AICREDITS_API_KEY is required for live runs")
        if run_id not in self.sessions:
            browser = await BrowserSession.start(run_id, run.principal)
            cookies = await browser.context.cookies("http://127.0.0.1:8102")
            register_session = next(item["value"] for item in cookies
                                    if item["name"] == "reg_session")
            probes = Probes(probe_key=self.settings.probe_key or "probe-demo",
                            register_session=register_session,
                            workspace=self.store.path.parent / "workspace", store=self.store)
            provider = Provider(base_url=self.settings.base_url, api_key=self.settings.api_key,
                                model=self.settings.model, ledger=self.ledger)
            self.sessions[run_id] = browser, probes, provider
        browser, probes, provider = self.sessions[run_id]
        trace = TraceWriter(self.store.path.parent / "traces", run_id,
                            model=self.settings.model, base_url=self.settings.base_url,
                            parameters={"max_tokens": 512}, prompt_hash=PROMPT_HASH)
        worker = WorkerLoop(store=self.store, provider=provider, browser=browser,
                            probes=probes,
                            workspace=WorkspaceFiles(self.store.path.parent / "workspace"),
                            portal_url="http://127.0.0.1:8101",
                            register_url="http://127.0.0.1:8102", trace=trace)
        try:
            await worker.run(run_id, answer=answer)
        finally:
            latest = self.store.get_run(run_id)
            if latest is None or latest.status in TERMINAL_STATUSES:
                await self.close_run(run_id)

    async def close_run(self, run_id: str) -> None:
        resources = self.sessions.pop(run_id, None)
        if resources:
            browser, probes, provider = resources
            await probes.close()
            await browser.close()
            await provider.close()

    async def close(self) -> None:
        for run_id in list(self.sessions):
            await self.close_run(run_id)
