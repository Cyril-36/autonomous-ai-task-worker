from datetime import date

from fastapi.testclient import TestClient

from sandbox.portal.app import create_app


def test_portal_detail_exposes_source_fields_and_probe_is_separate(tmp_path):
    app = create_app(tmp_path / "portal.db", reference_date=date(2026, 10, 3),
                     password="portal-test", probe_key="probe-test")
    with TestClient(app) as client:
        assert client.get("/invoices").status_code == 401
        assert client.post("/login", data={"password": "portal-test"}, follow_redirects=False).status_code == 303
        listing = client.get("/invoices")
        assert listing.status_code == 200
        assert "Larkspur Supplies" in listing.text
        assert "Next" in listing.text
        detail = client.get("/invoices/ls-1042")
        assert detail.status_code == 200
        assert 'data-doc-id="ls-1042"' in detail.text
        assert "<dt>Due date</dt>" in detail.text
        assert "₹48,250.00" in detail.text
        assert client.get("/api/invoices").status_code == 403
        probe = client.get("/api/invoices", headers={"X-Probe-Key": "probe-test"})
        assert probe.status_code == 200
        assert len(probe.json()) >= 14


def test_portal_messages_include_source_revision(tmp_path):
    app = create_app(tmp_path / "portal.db", reference_date=date(2026, 10, 3),
                     password="portal-test", probe_key="probe-test")
    with TestClient(app) as client:
        client.post("/login", data={"password": "portal-test"})
        page = client.get("/messages/msg-larkspur")
        assert page.status_code == 200
        assert 'data-kind="message"' in page.text
        assert "<dt>Remittance email</dt>" in page.text
