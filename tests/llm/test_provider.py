from decimal import Decimal
from types import SimpleNamespace

import pytest

from worker.config import ModelPrice, Pricing
from worker.llm.fake import FakeProvider
from worker.llm.ledger import Ledger
from worker.llm.provider import Provider, ProviderError, classify_error


@pytest.mark.parametrize(("status", "kind"), [
    (402, "credit"), (429, "rate_limited"), (500, "server"), (400, "bad_request"),
])
def test_error_classification(status, kind):
    assert classify_error(status_code=status) == kind


@pytest.mark.asyncio
async def test_fake_provider_resolves_name_against_latest_observation():
    fake = FakeProvider([{"tool": "browser_click", "target": "Save"}])
    response = await fake.complete(messages=[{"role": "tool", "content":
        '{"elements":[{"ref":"e17","name":"Save","role":"button"}]}'}],
        tools=[], max_tokens=128, run_id="r1")
    assert response.tool_calls[0]["arguments"]["ref"] == "e17"


@pytest.mark.asyncio
async def test_fake_provider_resolves_wrapped_snapshot():
    fake = FakeProvider([{"tool": "browser_click", "target": "Save"}])
    response = await fake.complete(messages=[{"role": "tool", "content":
        '<untrusted_page>{"elements":[{"ref":"e7","name":"Save"}]}</untrusted_page>'}],
        tools=[], max_tokens=128, run_id="r1")
    assert response.tool_calls[0]["arguments"]["ref"] == "e7"


@pytest.mark.asyncio
async def test_fake_provider_injects_error():
    fake = FakeProvider([{"error": "timeout"}])
    with pytest.raises(ProviderError) as error:
        await fake.complete(messages=[], tools=[], max_tokens=128, run_id="r1")
    assert error.value.kind == "timeout"


@pytest.mark.asyncio
async def test_provider_retries_each_call_through_ledger(tmp_path):
    class Create:
        attempts = 0

        async def create(self, **request):
            self.attempts += 1
            if self.attempts == 1:
                raise TimeoutError()
            usage = SimpleNamespace(model_dump=lambda: {"prompt_tokens": 2,
                                                          "completion_tokens": 1,
                                                          "cost": "0.001"}, model_extra={})
            message = SimpleNamespace(content="done", tool_calls=[])
            return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=message)],
                                   model="test")

    create = Create()
    client = SimpleNamespace(chat=SimpleNamespace(completions=create))
    pricing = Pricing("test", "today", Decimal(10), Decimal(10),
                      {"test": ModelPrice(Decimal(1), Decimal(1))})
    ledger = Ledger(tmp_path / "worker.db", pricing)
    provider = Provider(base_url="https://example.test/v1", api_key="fake", model="test",
                        ledger=ledger, client=client, retry_delay=0)
    result = await provider.complete(messages=[{"role": "user", "content": "hi"}],
                                     tools=[], max_tokens=10, run_id="r1")
    assert result.content == "done"
    assert [item.state for item in ledger.entries("r1")] == ["charged_unknown", "settled"]


@pytest.mark.asyncio
async def test_malformed_tool_arguments_are_returned_for_validation(tmp_path):
    class Create:
        async def create(self, **request):
            call = SimpleNamespace(id="c1", function=SimpleNamespace(name="browser_click",
                                                                      arguments="{bad json"))
            message = SimpleNamespace(content=None, tool_calls=[call])
            usage = SimpleNamespace(model_dump=lambda: {"prompt_tokens": 1,
                                                         "completion_tokens": 1}, model_extra={})
            return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=message)],
                                   model="test")

    client = SimpleNamespace(chat=SimpleNamespace(completions=Create()))
    pricing = Pricing("test", "today", Decimal(10), Decimal(10),
                      {"test": ModelPrice(Decimal(1), Decimal(1))})
    provider = Provider(base_url="https://example.test/v1", api_key="fake", model="test",
                        ledger=Ledger(tmp_path / "worker.db", pricing), client=client)
    result = await provider.complete(messages=[], tools=[], max_tokens=10, run_id="r1")
    assert result.tool_calls[0]["arguments"] == {}
    assert result.tool_calls[0]["invalid_arguments"]
