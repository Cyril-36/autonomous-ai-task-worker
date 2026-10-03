import pytest

from worker.runtime.apps import Apps

BASES = {"portal": "http://127.0.0.1:9001", "register": "http://127.0.0.1:9002"}


def test_builds_urls_from_named_pages():
    apps = Apps.load(BASES)
    assert apps.url("register", "new_invoice") == "http://127.0.0.1:9002/invoices/new"
    assert apps.url("portal", "invoice", "doc_ls1042") == "http://127.0.0.1:9001/invoices/doc_ls1042"


@pytest.mark.parametrize("app,page,page_id", [
    ("portal", "nope", None),
    ("portal", "invoice", None),
    ("portal", "invoice", "../admin"),
    ("portal", "invoice", "x/y"),
])
def test_rejects_unknown_pages_and_bad_ids(app, page, page_id):
    with pytest.raises(ValueError):
        Apps.load(BASES).url(app, page, page_id)


def test_description_has_no_routes_or_hosts():
    text = Apps.load(BASES).describe()
    assert "portal.invoice(id)" in text
    assert "/invoices" not in text and "127.0.0.1" not in text


def test_every_goal_type_has_a_procedure():
    from worker.contracts import GoalType
    apps = Apps.load(BASES)
    assert all(apps.procedure(goal.value).get("write") for goal in GoalType)
