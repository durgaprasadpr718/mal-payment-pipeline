"""Extract step: read each squad's raw CSV into a list of dict rows."""
from __future__ import annotations

import csv
from pathlib import Path


def read_csv(path: str | Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
