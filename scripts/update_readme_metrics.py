"""Copy generated eval metric tables into the README without hand-edited counts."""

from __future__ import annotations

import re
from pathlib import Path

from worker.config import ROOT

START = "<!-- EVAL_METRICS_START -->"
END = "<!-- EVAL_METRICS_END -->"


def _metrics(path: Path, label: str) -> str:
    if not path.is_file():
        return f"### {label}\n\nNot run yet."
    match = re.search(r"\| Metric \| Result \|\n(?:\|[^\n]*\|\n)+", path.read_text())
    if not match:
        raise ValueError(f"No metric table in {path}")
    return f"### {label}\n\n{match.group(0).rstrip()}"


def update_readme(readme: Path, fake: Path, live: Path) -> None:
    original = readme.read_text()
    if original.count(START) != 1 or original.count(END) != 1:
        raise ValueError("README metric markers must each appear once")
    generated = "\n\n".join([_metrics(fake, "Fake provider"),
                             _metrics(live, "Flash Lite live")])
    before, rest = original.split(START, 1)
    _, after = rest.split(END, 1)
    readme.write_text(before + START + "\n" + generated + "\n" + END + after)


if __name__ == "__main__":
    update_readme(ROOT / "README.md", ROOT / "evals" / "REPORT.md",
                  ROOT / "evals" / "LIVE_REPORT.md")
