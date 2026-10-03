import pytest

from worker.tools.browser import BrowserSession, StaleRef


@pytest.mark.asyncio
async def test_snapshot_captures_docs_and_hides_password():
    session = await BrowserSession.local_test("r1")
    try:
        await session.page.set_content("""
          <h1>Invoice</h1><article data-doc-id="d1" data-revision="2" data-kind="invoice">
          <dl><dt>Amount</dt><dd>₹48,250.00</dd></dl></article>
          <form action="/invoices" method="post"><label>Amount <input name="amount" value="48250.00"></label>
          <input type="hidden" name="form_token" value="abc">
          <label>Password <input type="password" name="password" value="secret-123"></label>
          <button>Save</button></form>
        """)
        observation = await session.snapshot()
        assert observation.documents[0].doc_id == "d1"
        assert observation.documents[0].fields[0].value == "₹48,250.00"
        assert "secret-123" not in observation.model_dump_json()
        assert "abc" not in observation.model_dump_json()
        save = next(item.ref for item in observation.elements if item.name == "Save")
        captured = await session.capture_form(save)
        assert captured["fields"]["form_token"] == "abc"
        assert "password" not in captured["fields"]
        assert captured["secret_fields"] == ["password"]
        await session.page.set_content("<h1>Different page</h1>")
        with pytest.raises(StaleRef):
            await session.click(save)
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_snapshot_hash_changes_when_live_form_value_changes():
    session = await BrowserSession.local_test("r1")
    try:
        await session.page.set_content('<label>Amount <input name="amount"></label>')
        first = await session.snapshot()
        await session.fill(first.elements[0].ref, "48250.00")
        second = await session.snapshot()
        assert first.content_hash != second.content_hash
    finally:
        await session.close()
