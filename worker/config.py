"""Runtime configuration; secrets stay in environment variables."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: Decimal
    output_per_million: Decimal
    cached_input_per_million: Decimal | None = None


@dataclass(frozen=True)
class Pricing:
    source: str
    date: str
    global_limit_inr: Decimal
    run_limit_inr: Decimal
    models: dict[str, ModelPrice]


def load_pricing(path: Path = ROOT / "config" / "pricing.toml") -> Pricing:
    with path.open("rb") as stream:
        raw = tomllib.load(stream)
    models = {
        name: ModelPrice(
            Decimal(str(values["input_per_million"])),
            Decimal(str(values["output_per_million"])),
            Decimal(str(values["cached_input_per_million"]))
            if "cached_input_per_million" in values
            else None,
        )
        for name, values in raw["models"].items()
    }
    return Pricing(
        source=raw["source"],
        date=raw["date"],
        global_limit_inr=Decimal(str(raw["global_limit_inr"])),
        run_limit_inr=Decimal(str(raw["run_limit_inr"])),
        models=models,
    )


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    base_url: str
    model: str
    api_key: str | None
    probe_key: str | None
    engine: str

    @classmethod
    def from_env(cls, *, data_dir: Path | None = None) -> Settings:
        return cls(
            data_dir=data_dir or Path(os.getenv("DATA_DIR", ROOT / "data")),
            base_url=os.getenv("LLM_BASE_URL", "https://api.aicredits.in/v1"),
            model=os.getenv("LLM_MODEL", "google/gemini-2.5-flash-lite"),
            api_key=os.getenv("AICREDITS_API_KEY"),
            probe_key=os.getenv("PROBE_KEY"),
            engine=os.getenv("WORKER_ENGINE", "replay"),
        )
