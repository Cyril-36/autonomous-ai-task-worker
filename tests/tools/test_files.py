import pytest

from worker.tools.files import WorkspaceFiles


def test_workspace_read_and_gated_export(tmp_path):
    files = WorkspaceFiles(tmp_path)
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "note.txt").write_text("hello")
    assert files.read("inbox/note.txt") == "hello"
    assert files.list("inbox") == ["note.txt"]
    target = files.write_csv("invoices.csv", [{"invoice_number": "LS-1042", "amount": "48250.00"}])
    assert target.read_text().splitlines() == ["invoice_number,amount", "LS-1042,48250.00"]


@pytest.mark.parametrize("name", ["../escape.csv", "bad name.csv", "x.txt", "/tmp/x.csv"])
def test_export_filename_cannot_escape(tmp_path, name):
    with pytest.raises(ValueError):
        WorkspaceFiles(tmp_path).write_csv(name, [{"a": "b"}])
