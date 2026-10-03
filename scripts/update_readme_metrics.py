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


def update_readme(readme: Path, fake: Path, live: Path,
                  extra: list[tuple[Path, str]] | None = None) -> None:
    original = readme.read_text()
    if original.count(START) != 1 or original.count(END) != 1:
        raise ValueError("README metric markers must each appear once")
    sections = [(fake, "Scripted fake model (free, deterministic)"),
                (live, "Development pass, live")] + list(extra or [])
    generated = "\n\n".join(_metrics(path, label) for path, label in sections)
    before, rest = original.split(START, 1)
    _, after = rest.split(END, 1)
    readme.write_text(before + START + "\n" + generated + "\n" + END + after)


EVALS = ROOT / "evals"

if __name__ == "__main__":
    update_readme(ROOT / "README.md", EVALS / "REPORT.md", EVALS / "LIVE_DEV_AUDITED.md", [
        (EVALS / "LIVE_HELDOUT.md", "Held-out tasks, live, run once (writes audited only in refusal cases)"),
        (EVALS / "LIVE_UNDERSTANDING_AUDITED.md", "Request understanding, live, latest pass"),
        (EVALS / "LIVE_UNDERSTANDING_X2.md", "Request understanding, live, two earlier repeats"),
        (EVALS / "LIVE_REPORT.md", "Before generalization: development pass, live"),
    ])
