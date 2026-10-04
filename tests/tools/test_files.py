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
        "due_date": "2026-11-01", "ignored": "not exported"}],
        run_id="run-1", mutation_id="abc123")
    assert target.relative_to(tmp_path).as_posix() == "exports/run-1/abc123-invoices.csv"
    assert target.read_text().splitlines() == [
        "supplier_id,invoice_number,amount,currency,due_date",
        "larkspur-supplies,LS-1042,48250.00,INR,2026-11-01",
    ]
    assert files.write_csv("empty.csv", [], run_id="run-1", mutation_id="def456").read_text() == (
        "supplier_id,invoice_number,amount,currency,due_date\n"
    )


def test_same_export_name_from_other_runs_cannot_overwrite_prior_evidence(tmp_path):
    files = WorkspaceFiles(tmp_path)
    row = {"supplier_id": "s1", "invoice_number": "I-1", "amount": "1", "currency": "INR",
           "due_date": "2026-11-01"}
    first = files.write_csv("invoices.csv", [row], run_id="r1", mutation_id="a1")
    second = files.write_csv("invoices.csv", [{**row, "amount": "2"}],
                             run_id="r2", mutation_id="a2")
    assert first != second
    assert ",1,INR," in first.read_text()
    assert ",2,INR," in second.read_text()
    with pytest.raises(FileExistsError):
        files.write_csv("invoices.csv", [{**row, "amount": "3"}],
                        run_id="r1", mutation_id="a1")
    assert ",1,INR," in first.read_text()


@pytest.mark.parametrize("name", ["../escape.csv", "bad name.csv", "x.txt", "/tmp/x.csv"])
def test_export_filename_cannot_escape(tmp_path, name):
    with pytest.raises(ValueError):
        WorkspaceFiles(tmp_path).write_csv(name, [{"a": "b"}],
                                            run_id="r1", mutation_id="a1")
