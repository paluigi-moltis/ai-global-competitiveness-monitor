"""OpenRouter collector - daily model usage rankings.

Endpoint: GET /api/v1/datasets/rankings-daily (Data API, CC BY 4.0)
Docs: https://openrouter.ai/docs/cookbook/administration/data-api

Requires any valid OpenRouter API key (env var OPENROUTER_API_KEY).
Returns the top 50 public models per day by total tokens plus an
aggregated "other" row. Historical coverage from 2025-01-01; max span
366 days per request; rate limit 30 req/min, 500 req/day.

Data-quality notes (spec §7):
- "other" is excluded from geographical calculations; we keep it so the
  identifiable share of traffic can be reported.
- total_tokens = prompt + completion tokens; tokenisation differs across
  providers so cross-provider comparisons are approximate.
- estimated_spend is NOT reconstructed here; if added later it must use an
  explicit input/output mix assumption and archived prices (experimental,
  zero weight by default).

Attribution (required when republishing):
  Source: OpenRouter (openrouter.ai/rankings), as of <meta.as_of>.
  Licensed under CC BY 4.0.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import time

from collectors.base import archive_raw, http_get_json

log = logging.getLogger("openrouter")

BASE = "https://openrouter.ai/api/v1/datasets/rankings-daily"
HIST_START = dt.date(2025, 1, 1)
MAX_SPAN = 366  # API limit per request


def _api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY not set - the rankings-daily Data API requires "
            "any valid OpenRouter key (https://openrouter.ai/settings/keys)")
    return key


def _windows(start: dt.date, end: dt.date):
    """Yield (win_start, win_end) chunks respecting the 366-day span limit."""
    cursor = start
    while cursor <= end:
        win_end = min(cursor + dt.timedelta(days=MAX_SPAN - 1), end)
        yield cursor, win_end
        cursor = win_end + dt.timedelta(days=1)


def collect(days: int | None = None) -> list[dict]:
    """Collect daily token rankings; `days` = trailing window (default 30).

    Rows: {_dataset: usage, date, source_model_id, tokens}
    The aggregated "other" bucket is emitted as source_model_id="other"
    (deliberately unmappable, so process.py excludes it from geographical
    shares and reports the identifiable traffic share).
    """
    key = _api_key()
    today = dt.date.today()
    window = days if days is not None else 30
    start = max(HIST_START, today - dt.timedelta(days=window - 1))
    rows: list[dict] = []
    for win_start, win_end in _windows(start, today):
        payload = http_get_json(
            BASE,
            params={"start_date": win_start.isoformat(),
                    "end_date": win_end.isoformat()},
            headers={"Authorization": f"Bearer {key}"},
        )
        archive_raw("openrouter", payload,
                    label=f"rankings-daily_{win_start}_{win_end}")
        data = payload.get("data", [])
        as_of = payload.get("meta", {}).get("as_of", "unknown")
        log.info("OpenRouter rankings-daily %s..%s: %d rows (as_of %s)",
                 win_start, win_end, len(data), as_of)
        for entry in data:
            slug = entry.get("model_permaslug")
            tokens = entry.get("total_tokens")
            if not slug or tokens is None:
                continue
            rows.append({
                "_dataset": "usage",
                "date": entry.get("date", win_start.isoformat()),
                "source_model_id": slug,
                "tokens": float(tokens),
            })
        # rate limits: 30 req/min - sleep briefly between windowed requests
        time.sleep(2.5)
    return rows
