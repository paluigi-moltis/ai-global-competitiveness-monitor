"""Shared collector helpers: raw archiving, HTTP with retries, config reads."""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import requests

from common import RAW_DIR


def archive_raw(source: str, payload, label: str | None = None) -> Path:
    """Store an original source response under data/raw/<source>/<date>/[label].json."""
    day = dt.date.today().isoformat()
    out_dir = RAW_DIR / source / day
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{label or 'response'}.json"
    path = out_dir / name
    if isinstance(payload, (dict, list)):
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        path.write_text(str(payload))
    return path


def http_get_json(url: str, *, params: dict | None = None, headers: dict | None = None,
                  retries: int = 3, backoff: float = 2.0, timeout: int = 60):
    """GET with simple exponential backoff. Returns parsed JSON."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(backoff ** attempt)
    raise RuntimeError(f"GET {url} failed after {retries} attempts: {last_exc}")


def csv_rows(path: Path) -> list[dict]:
    """Read a downloaded CSV/TSV file into dicts (for non-API sources)."""
    import csv
    with path.open(newline="", encoding="utf-8") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
        return list(csv.DictReader(fh, dialect=dialect))
