from fastapi.testclient import TestClient

from worker.console.app import create_app


def client_for(tmp_path):
    return TestClient(create_app(tmp_path / "worker.db", passwords={
        "asha@example.com": "asha-test", "ravi@example.com": "ravi-test",
        "meera@example.com": "meera-test",
    }))


def login(client, email="ravi@example.com", password="ravi-test"):
    response = client.post("/api/session", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()


def test_session_and_errors_follow_frozen_contract(tmp_path):
    with client_for(tmp_path) as client:
        assert len(client.get("/api/demo-users").json()) == 3
        assert client.get("/api/me").json() == {"error": {"code": "not_signed_in", "message": "Sign in required"}}
        bad = client.post("/api/session", json={"email": "ravi@example.com", "password": "wrong"})
        assert bad.status_code == 401
        assert bad.json()["error"]["code"] == "bad_credentials"
        principal = login(client)
        assert principal["email"] == "ravi@example.com"
        assert client.get("/api/me").json() == principal
        assert client.delete("/api/session").status_code == 204
        assert client.get("/api/me").status_code == 401


def test_runs_visibility_detail_and_validation(tmp_path):
    with client_for(tmp_path) as client:
        login(client)
        assert client.post("/api/runs", json={"request": ""}).status_code == 422
        response = client.post("/api/runs", json={"request": "Register the latest Larkspur invoice"})
        assert response.status_code == 201
        run_id = response.json()["run_id"]
        assert client.get("/api/runs").json()[0]["run_id"] == run_id
        detail = client.get(f"/api/runs/{run_id}").json()
        assert set(detail) == {"summary", "contract", "plan", "facts", "approvals", "question",
                               "verification", "pending", "budget", "last_seq"}
        events = client.get(f"/api/runs/{run_id}/events?after=1").json()
        assert events and all(event["seq"] > 1 for event in events)
        assert client.post(f"/api/runs/{run_id}/answer", json={"text": "yes"}).status_code == 409
        client.delete("/api/session")
        login(client, "meera@example.com", "meera-test")
        assert client.get(f"/api/runs/{run_id}").status_code == 403
        client.delete("/api/session")
        login(client, "asha@example.com", "asha-test")
        assert client.get(f"/api/runs/{run_id}").status_code == 200


def test_replay_question_approval_and_cancel(tmp_path):
    with client_for(tmp_path) as client:
        login(client)
        question = client.post("/api/runs", json={"request": "Which Larkspur supplier?"}).json()
        question_id = question["run_id"]
        detail = client.get(f"/api/runs/{question_id}").json()
        assert detail["summary"]["status"] == "awaiting_input"
        assert detail["question"]["question_id"]
        assert client.post(f"/api/runs/{question_id}/answer", json={"text": "Larkspur Supplies"}).status_code == 202
        assert client.get(f"/api/runs/{question_id}").json()["summary"]["status"] == "completed"
        approval = client.post("/api/runs", json={"request": "Register a large Brightfen invoice"}).json()
        approval_id = client.get(f"/api/runs/{approval['run_id']}").json()["approvals"][0]["approval_id"]
        assert client.post(f"/api/runs/{approval['run_id']}/approvals/{approval_id}",
                           json={"decision": "reject"}).json()["status"] == "rejected"
        assert client.get(f"/api/runs/{approval['run_id']}").json()["summary"]["status"] == "blocked"
        waiting = client.post("/api/runs", json={"request": "Which Larkspur supplier?"}).json()
        assert client.post(f"/api/runs/{waiting['run_id']}/cancel").status_code == 202


def test_budget_examples_and_artifact_error(tmp_path):
    with client_for(tmp_path) as client:
        login(client)
        assert client.get("/api/examples").json()
        assert client.get("/api/budget").json()["estimated"] is True
        run = client.post("/api/runs", json={"request": "Check invoice BF-2291"}).json()
        assert client.get(f"/api/runs/{run['run_id']}/artifacts/missing.png").status_code == 404
