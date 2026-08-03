"""Extrato em CSV. Formato legível, não JSON de API."""
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path


def _fmt(v):
    if isinstance(v, Decimal):
        return f"{v:.6f}"
    return "" if v is None else v


def export_csv(rows: list[dict], path: str | Path) -> str:
    path = Path(path)
    if not rows:
        path.write_text("", encoding="utf-8")
        return str(path)
    cols = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: _fmt(r.get(k)) for k in cols})
    return str(path)
