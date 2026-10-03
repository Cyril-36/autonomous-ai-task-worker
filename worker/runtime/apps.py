"""Company context loaded from config/apps.yaml: apps, their pages, and per-goal procedures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from worker.config import ROOT

MANIFEST = ROOT / "config" / "apps.yaml"


@dataclass(frozen=True)
class Page:
    app: str
    name: str
    path: str
    about: str

    @property
    def needs_id(self) -> bool:
        return "{id}" in self.path


class Apps:
    def __init__(self, raw: dict, base_urls: dict[str, str]):
        self.raw = raw
        self.base_urls = base_urls
        self.pages: dict[tuple[str, str], Page] = {
            (app, name): Page(app, name, spec["path"], spec["about"])
            for app, body in raw["apps"].items()
            for name, spec in body["pages"].items()
        }

    @classmethod
    def load(cls, base_urls: dict[str, str], path: Path = MANIFEST) -> Apps:
        return cls(yaml.safe_load(path.read_text()), base_urls)

    def url(self, app: str, page: str, page_id: str | None = None) -> str:
        spec = self.pages.get((app, page))
        if spec is None:
            known = ", ".join(f"{a}.{p}" for a, p in self.pages)
            raise ValueError(f"Unknown page {app}.{page}. Known pages: {known}")
        if app not in self.base_urls:
            raise ValueError(f"App {app} is not available in this run")
        if spec.needs_id:
            if not page_id:
                raise ValueError(f"{app}.{page} needs an id")
            if "/" in page_id or "?" in page_id or ".." in page_id:
                raise ValueError("Invalid id")
            return self.base_urls[app] + spec.path.replace("{id}", page_id)
        return self.base_urls[app] + spec.path

    def procedure(self, goal_type: str) -> dict[str, str]:
        return self.raw["procedures"].get(goal_type, {})

    def describe(self) -> str:
        """Compact, route-free description for the model."""
        lines = []
        for app, body in self.raw["apps"].items():
            lines.append(f"{app}: {body['title']}. {body['purpose']}")
            for name, spec in body["pages"].items():
                arg = "(id)" if "{id}" in spec["path"] else ""
                lines.append(f"  - {app}.{name}{arg}: {spec['about']}")
        return "\n".join(lines)
