from datetime import date

import pytest
from fastapi.testclient import TestClient

from sandbox.register.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "register.db", reference_date=date(2026, 10, 3), timeout_delay=0.01,
                     passwords={"asha@example.com": "asha-test", "ravi@example.com": "ravi-test",
                                "meera@example.com": "meera-test"})
    with TestClient(app) as value:
        yield value


def sign_in(client, email, password):
    response = client.post("/login", data={"email": email, "password": password}, follow_redirects=False)
    assert response.status_code == 303
    return response.cookies["reg_session"]


def token_from(page):
    return page.split('name="form_token" value="')[1].split('"')[0]


def invoice_form(token, supplier="larkspur-supplies", number="LS-1042", due="2026-11-01"):
    return {"form_token": token, "supplier_id": supplier, "invoice_number": number,
            "amount": "48250.00", "currency": "INR", "due_date": due,
            "source_doc_id": "ls-1042"}


def test_assigned_operator_creates_and_duplicate_conflicts(client):
    sign_in(client, "ravi@example.com", "ravi-test")
    token = token_from(client.get("/invoices/new").text)
    response = client.post("/invoices", data=invoice_form(token), follow_redirects=False)
    assert response.status_code == 303
    assert client.get("/api/invoices").json()[-1]["invoice_number"] == "LS-1042"
    second = token_from(client.get("/invoices/new").text)
    duplicate = client.post("/invoices", data=invoice_form(second))
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.text


def test_unassigned_operator_denied_via_html_and_api(client):
    token = sign_in(client, "meera@example.com", "meera-test")
    form_token = token_from(client.get("/invoices/new").text)
    html = client.post("/invoices", data=invoice_form(form_token))
    assert html.status_code == 403
    assert "not assigned" in html.text
    api = client.post("/api/invoices", json=invoice_form(form_token),
                      headers={"Authorization": f"Bearer {token}"})
    assert api.status_code == 403
    assert "not assigned" in api.json()["detail"]


def test_policy_requires_admin(client):
    sign_in(client, "ravi@example.com", "ravi-test")
    assert client.post("/policy", data={"threshold": "50000"}).status_code == 403
    sign_in(client, "asha@example.com", "asha-test")
    assert client.post("/policy", data={"threshold": "50000"}).status_code == 200


def test_operation_token_is_single_use_and_can_be_voided(client):
    token = sign_in(client, "ravi@example.com", "ravi-test")
    form_token = token_from(client.get("/invoices/new").text)
    headers = {"Authorization": f"Bearer {token}"}
    void = client.post(f"/api/operations/{form_token}/void", headers=headers)
    assert void.json()["status"] == "voided"
    assert client.post("/invoices", data=invoice_form(form_token)).status_code == 409
    fresh = token_from(client.get("/invoices/new").text)
    assert client.post("/invoices", data=invoice_form(fresh), follow_redirects=False).status_code == 303
    assert client.get(f"/api/operations/{fresh}", headers=headers).json()["status"] == "committed"
    assert client.post(f"/api/operations/{fresh}/void", headers=headers).json()["status"] == "committed"
    assert client.post("/invoices", data=invoice_form(fresh)).status_code == 409


def test_stale_version_and_corrupt_fault(client):
    admin = sign_in(client, "asha@example.com", "asha-test")
    headers = {"Authorization": f"Bearer {admin}"}
    client.post("/api/_faults", json={"corrupt_next_save": True}, headers=headers)
    fresh = token_from(client.get("/invoices/new").text)
    assert client.post("/invoices", data=invoice_form(fresh), follow_redirects=False).status_code == 303
    saved = next(row for row in client.get("/api/invoices").json()
                 if row["invoice_number"] == "LS-1042")
    assert saved["due_date"] == "2026-11-02"
    edit = client.get(f"/invoices/{saved['id']}/edit")
    stale = client.post(f"/invoices/{saved['id']}", data={**invoice_form(token_from(edit.text)), "version": "0"})
    assert stale.status_code == 409


def test_layout_variant_and_commit_then_timeout(client):
    admin = sign_in(client, "asha@example.com", "asha-test")
    headers = {"Authorization": f"Bearer {admin}"}
    client.post("/api/_faults", json={"layout_variant": "b", "commit_then_timeout": True}, headers=headers)
    page = client.get("/invoices/new")
    assert "Record invoice" in page.text
    token = token_from(page.text)
    result = client.post("/invoices", data=invoice_form(token), follow_redirects=False)
    assert result.status_code == 303
    assert client.post(f"/api/operations/{token}/void", headers=headers).json()["status"] == "committed"
