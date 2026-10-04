"""Read a bounded workspace and write validated CSV exports."""

from __future__ import annotations

import csv
import re
from pathlib import Path

FILENAME = re.compile(r"^[a-z0-9_-]{1,60}\.csv$")
RUN_ID = re.compile(r"^[A-Za-z0-9_#-]{1,120}$")
MUTATION_ID = re.compile(r"^[a-fA-F0-9]{1,64}$")
EXPORT_COLUMNS = ("supplier_id", "invoice_number", "amount", "currency", "due_date")


class WorkspaceFiles:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _inside(self, path: str) -> Path:
        target = (self.root / path).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Path leaves workspace")
        return target

    def list(self, path: str = ".") -> list[str]:
        target = self._inside(path)
        if not target.is_dir():
            raise FileNotFoundError(path)
        return sorted(item.name for item in target.iterdir())

    def read(self, path: str) -> str:
        target = self._inside(path)
        if not target.is_file():
            raise FileNotFoundError(path)
        return target.read_text(encoding="utf-8")

    def write_csv(self, name: str, rows: list[dict[str, str]], *,
                  run_id: str, mutation_id: str) -> Path:
        if (not FILENAME.fullmatch(name) or not RUN_ID.fullmatch(run_id)
                or not MUTATION_ID.fullmatch(mutation_id)):
            raise ValueError("Invalid export identity or filename")
        target = self._inside(f"exports/{run_id}/{mutation_id}-{name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=EXPORT_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row[column] for column in EXPORT_COLUMNS})
        return target
