import pytest

from worker.tools.files import WorkspaceFiles


def test_workspace_read_and_gated_export(tmp_path):
    files = WorkspaceFiles(tmp_path)
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "note.txt").write_text("hello")
    assert files.read("inbox/note.txt") == "hello"
    assert files.list("inbox") == ["note.txt"]
    target = files.write_csv("invoices.csv", [{"supplier_id": "larkspur-supplies",
        "invoice_number": "LS-1042", "amount": "48250.00", "currency": "INR",
        "due_date": "2026-11-01", "ignored": "not exported"}])
    assert target.read_text().splitlines() == [
        "supplier_id,invoice_number,amount,currency,due_date",
        "larkspur-supplies,LS-1042,48250.00,INR,2026-11-01",
    ]
    assert files.write_csv("empty.csv", []).read_text() == (
        "supplier_id,invoice_number,amount,currency,due_date\n"
    )


@pytest.mark.parametrize("name", ["../escape.csv", "bad name.csv", "x.txt", "/tmp/x.csv"])
def test_export_filename_cannot_escape(tmp_path, name):
    with pytest.raises(ValueError):
        WorkspaceFiles(tmp_path).write_csv(name, [{"a": "b"}])
