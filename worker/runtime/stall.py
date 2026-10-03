"""Progress-based stall detection."""

from __future__ import annotations

import json


class StallDetector:
    def __init__(self):
        self.last_call: str | None = None
        self.repeats = 0
        self.no_progress = 0
        self.reflections = 0

    def observe(self, tool: str, arguments: dict, *, progress: bool) -> str | None:
        key = json.dumps([tool, arguments], sort_keys=True)
        self.repeats = self.repeats + 1 if key == self.last_call else 1
        self.last_call = key
        if progress:
            self.no_progress = 0
            self.repeats = 0
            return None
        self.no_progress += 1
        if self.repeats >= 3 or self.no_progress >= 6:
            self.repeats = 0
            self.no_progress = 0
            self.reflections += 1
            return "ask_user" if self.reflections > 1 else "reflect"
        return None
