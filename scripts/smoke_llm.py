"""The only T1 live provider calls. Requires a locally configured API key."""

from __future__ import annotations

import asyncio
from decimal import Decimal

from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAIError

from worker.config import Settings, load_pricing

TOOL = {
    "type": "function",
    "function": {
        "name": "get_time",
        "description": "Returns the current time",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}


def estimated_cost(prompt_tokens: int, completion_tokens: int, model: str) -> Decimal:
    price = load_pricing().models[model]
    return (
        Decimal(prompt_tokens) * price.input_per_million
        + Decimal(completion_tokens) * price.output_per_million
    ) / Decimal(1_000_000)


async def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    if not settings.api_key:
        raise SystemExit("AICREDITS_API_KEY is missing; configure it locally before smoke")
    urls = [settings.base_url]
    fallback = "https://aicredits.in/v1"
    if fallback not in urls:
        urls.append(fallback)
    for base_url in urls:
        client = AsyncOpenAI(base_url=base_url, api_key=settings.api_key, max_retries=0, timeout=60)
        try:
            outputs = []
            for extra in ({}, {"reasoning_effort": "low"}):
                response = await client.chat.completions.create(
                    model=settings.model,
                    messages=[{"role": "user", "content": "Call get_time now."}],
                    tools=[TOOL],
                    tool_choice="required",
                    max_tokens=256,
                    **extra,
                )
                usage = response.usage
                outputs.append((extra, response, usage))
            for extra, response, usage in outputs:
                print(
                    {
                        "endpoint": base_url,
                        "model": response.model,
                        "reasoning_effort": extra.get("reasoning_effort", "unset"),
                        "tool_call": bool(response.choices[0].message.tool_calls),
                        "usage": usage.model_dump() if usage else None,
                        "estimated_cost_inr": str(
                            estimated_cost(usage.prompt_tokens, usage.completion_tokens, settings.model)
                        ) if usage else "unknown",
                    }
                )
            return
        except OpenAIError as exc:
            print(f"{base_url}: {type(exc).__name__}")
        finally:
            await client.close()
    raise SystemExit("Smoke failed on both configured endpoints")


if __name__ == "__main__":
    asyncio.run(main())
