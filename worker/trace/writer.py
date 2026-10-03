"""Append-only redacted JSONL trace per run."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def _clean(value):
    if isinstance(value, dict):
        return {key: "•••" if key in {"form_token", "password", "cookie", "api_key"}
                else _clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    return value


class TraceWriter:
    def __init__(self, root: Path | str, run_id: str, *, model: str, base_url: str,
                 parameters: dict, prompt_hash: str):
        path = Path(root)
        path.mkdir(parents=True, exist_ok=True)
        self.path = path / f"{run_id}.jsonl"
        if not self.path.exists():
            self.append("header", {"model": model, "base_url": base_url,
                                   "parameters": parameters, "prompt_hash": prompt_hash})

    def append(self, kind: str, data: dict) -> None:
        line = {"ts": datetime.now(UTC).isoformat(), "type": kind, **_clean(data)}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
