"""Scripted model for deterministic, zero-cost worker tests."""

from __future__ import annotations

import json
from collections import deque

from worker.llm.provider import ProviderError, ProviderResponse


def _latest_elements(messages: list[dict]) -> list[dict]:
    for message in reversed(messages):
        content = message.get("content")
        if not isinstance(content, str):
            continue
        try:
            data = json.loads(content)
        except ValueError:
            continue
        if isinstance(data, dict) and "elements" in data:
            return data["elements"]
    return []


class FakeProvider:
    def __init__(self, script: list[dict]):
        self.script = deque(script)
        self.model = "fake"

    async def complete(self, *, messages: list[dict], tools: list[dict],
                       max_tokens: int, run_id: str) -> ProviderResponse:
        if not self.script:
            raise ProviderError("script_exhausted")
        step = self.script.popleft()
        if "error" in step:
            raise ProviderError(step["error"])
        if "content" in step:
            return ProviderResponse(step["content"], [], "fake", None)
        arguments = dict(step.get("arguments", {}))
        if "target" in step:
            matches = [item for item in _latest_elements(messages)
                       if item.get("name") == step["target"]]
            if len(matches) != 1:
                raise ProviderError("target_missing")
            arguments["ref"] = matches[0]["ref"]
        return ProviderResponse(None, [{"id": step.get("id", "fake-call"),
                                        "name": step["tool"], "arguments": arguments}],
                                "fake", None)
