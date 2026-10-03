import time

from fastapi.testclient import TestClient

from worker.config import load_pricing
from worker.console.app import create_app
from worker.console.service import RunService
from worker.llm.ledger import Ledger
from worker.store import Store


def test_live_mode_enqueues_and_streams_worker_result(tmp_path):
    async def fake_runner(run_id, answer=None):
        store.update_run(run_id, status="blocked", phase="done")
        store.append_event(run_id, "run_status", {
            "status": "blocked", "reason": "Fake runner completed without a verified write.",
        })

    app = create_app(tmp_path / "worker.db", engine="live", runner=fake_runner)
    store = app.state.service.store
    with TestClient(app) as client:
        signed = client.post("/api/session", json={"email": "ravi@example.com",
                                                     "password": "ravi-demo"})
        assert signed.status_code == 200
        response = client.post("/api/runs", json={"request": "Register latest invoice"})
        assert response.status_code == 201
        run_id = response.json()["run_id"]
        for _ in range(100):
            if client.get(f"/api/runs/{run_id}").json()["summary"]["status"] == "blocked":
                break
            time.sleep(0.01)
        assert client.get(f"/api/runs/{run_id}").json()["summary"]["status"] == "blocked"
        events = client.get(f"/api/runs/{run_id}/events").json()
        assert events[-1]["data"]["reason"] == "Fake runner completed without a verified write."


def test_static_console_fallback_and_unknown_api_json(tmp_path):
    app = create_app(tmp_path / "worker.db", engine="replay")
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert "<html" in client.get("/runs/example").text.lower()
        response = client.get("/api/does-not-exist")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


def test_live_budget_reads_persisted_ledger(tmp_path):
    store = Store(tmp_path / "worker.db")
    ledger = Ledger(store.path, load_pricing())
    request = {"messages": [{"role": "user", "content": "hello"}], "max_tokens": 256}
    entry = ledger.reserve("r1", "google/gemini-2.5-flash-lite", request)
    service = RunService(store, engine="live", model="google/gemini-2.5-flash-lite",
                         ledger=ledger)
    assert float(service.budget()["global_reserved_inr"]) > 0
    ledger.settle(entry.entry_id, {"prompt_tokens": 5, "completion_tokens": 5,
                                   "cost": "0.014"})
    assert service.budget("r1")["run_spent_inr"] == "0.01"


def test_artifact_is_served_only_to_run_owner(tmp_path):
    app = create_app(tmp_path / "worker.db", engine="replay")
    with TestClient(app) as client:
        client.post("/api/session", json={"email": "ravi@example.com", "password": "ravi-demo"})
        run_id = client.post("/api/runs", json={"request": "Register latest invoice"}).json()["run_id"]
        folder = tmp_path / "artifacts" / run_id
        folder.mkdir(parents=True)
        (folder / "step-1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        response = client.get(f"/api/runs/{run_id}/artifacts/step-1.png")
        assert response.status_code == 200
        assert response.content.startswith(b"\x89PNG")
        client.post("/api/session", json={"email": "meera@example.com",
                                           "password": "meera-demo"})
        assert client.get(f"/api/runs/{run_id}/artifacts/step-1.png").status_code == 403
