"""OpenAI-compatible gateway adapter with ledgered retries."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from worker.llm.ledger import Ledger


class ProviderError(Exception):
    def __init__(self, kind: str):
        self.kind = kind
        super().__init__(kind)


def classify_error(*, status_code: int | None = None, error: BaseException | None = None) -> str:
    if isinstance(error, (APITimeoutError, asyncio.TimeoutError, httpx.TimeoutException)):
        return "timeout"
    if status_code in {402, 403}:
        return "credit"
    if status_code == 429:
        return "rate_limited"
    if status_code is not None and status_code >= 500:
        return "server"
    if isinstance(error, APIConnectionError):
        return "server"
    return "bad_request"


@dataclass(frozen=True)
class ProviderResponse:
    content: str | None
    tool_calls: list[dict[str, Any]]
    model: str
    usage: dict[str, Any] | None
    entry_id: str | None = None


class Provider:
    def __init__(self, *, base_url: str, api_key: str, model: str, ledger: Ledger,
                 client: Any | None = None, retry_delay: float = 0.5):
        self.client = client or AsyncOpenAI(base_url=base_url, api_key=api_key,
                                           max_retries=0, timeout=60)
        self.model = model
        self.ledger = ledger
        self.retry_delay = retry_delay

    async def close(self) -> None:
        await self.client.close()

    async def complete(self, *, messages: list[dict], tools: list[dict],
                       max_tokens: int, run_id: str) -> ProviderResponse:
        request = {"model": self.model, "messages": messages, "tools": tools,
                   "tool_choice": "required", "max_tokens": max_tokens}
        for attempt in range(3):
            entry = self.ledger.reserve(run_id, self.model, request)
            try:
                response = await self.client.chat.completions.create(**request)
            except (TimeoutError, APIStatusError, APIConnectionError, APITimeoutError, httpx.TimeoutException) as exc:
                self.ledger.settle(entry.entry_id, None)
                kind = classify_error(status_code=getattr(exc, "status_code", None), error=exc)
                if kind in {"timeout", "rate_limited", "server"} and attempt < 2:
                    await asyncio.sleep(self.retry_delay * 2**attempt)
                    continue
                raise ProviderError(kind) from exc
            usage = response.usage.model_dump() if response.usage else None
            if usage and response.usage.model_extra:
                usage.update(response.usage.model_extra)
            self.ledger.settle(entry.entry_id, usage)
            message = response.choices[0].message
            calls = []
            for call in message.tool_calls or []:
                try:
                    arguments = json.loads(call.function.arguments)
                    invalid = not isinstance(arguments, dict)
                except ValueError:
                    arguments, invalid = {}, True
                calls.append({"id": call.id, "name": call.function.name,
                              "arguments": arguments if not invalid else {},
                              "invalid_arguments": invalid})
            return ProviderResponse(message.content, calls, response.model, usage, entry.entry_id)
        raise ProviderError("server")
