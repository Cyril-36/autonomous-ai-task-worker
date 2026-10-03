from tests.console.test_api import client_for, login


def test_sse_replays_from_last_event_and_ends(tmp_path):
    with client_for(tmp_path) as client:
        login(client)
        run = client.post("/api/runs", json={"request": "Register latest Larkspur Supplies invoice"}).json()
        run_id = run["run_id"]
        events = client.get(f"/api/runs/{run_id}/events").json()
        stream = client.get(f"/api/runs/{run_id}/stream", headers={"Last-Event-ID": "1"})
        assert stream.status_code == 200
        assert "text/event-stream" in stream.headers["content-type"]
        assert "id: 1\n" not in stream.text
        assert f"id: {events[-1]['seq']}" in stream.text
        assert "event: end" in stream.text
        for forbidden in ("form_token", "ravi-test", "console_session", "reg_session"):
            assert forbidden not in stream.text
