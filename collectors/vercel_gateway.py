"""Vercel AI Gateway collector - model usage leaderboards.

Endpoint: GET https://vercel.com/api/ai/leaderboard-export
Docs: https://vercel.com/docs/ai-gateway/leaderboards
Public, NO authentication. CC BY 4.0 licensed, cached 24h.

Returns DAILY PERCENTAGE SHARES (not absolute volumes) of tokens,
requests and spend per model - anonymised gateway-wide usage data.
History available from 2025-10-01.

Data-quality notes:
- Only shares are published: we store them as a `usage_shares` dataset and
  never fabricate absolute token/spend values from them.
- Shares sum to 100% per (date, metric) INCLUDING the aggregated "Other"
  row; geographical calculations exclude "Other" and report the
  identifiable share, mirroring the OpenRouter treatment.
- Model names are display names ("GLM 5.3"), mapped via model_mapping.csv;
  the `labs` dataset has clean creator slugs used for provider-level
  attribution cross-checks.
- Gateway self-selection: reflects traffic routed through Vercel AI Gateway
  only - a skewed but public sample of the market, documented as such.

Attribution (required when republishing):
  © 2026 Vercel. "AI Gateway Leaderboard Data" is licensed under
  CC BY 4.0. https://creativecommons.org/licenses/by/4.0/
"""
from __future__ import annotations

import datetime as dt
import json
import logging

from collectors.base import archive_raw, http_get_json

log = logging.getLogger("vercel_gateway")

EXPORT_URL = "https://vercel.com/api/ai/leaderboard-export"
HIST_START = dt.date(2025, 10, 1)  # earliest_available_date per docs
METRICS = ("tokens", "requests", "spend")  # usage-relevant metrics


def _fetch_range(from_date: dt.date, to_date: dt.date) -> dict:
    params = {
        "dataset": "models",
        "modality": "text",
        "format": "json",
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
    }
    payload = http_get_json(EXPORT_URL, params=params)
    archive_raw("vercel_gateway", payload,
                label=f"leaderboard_models_{from_date}_{to_date}")
    return payload


def collect(days: int | None = None) -> list[dict]:
    """Collect daily model usage shares; `days` = trailing window (default 60).

    Rows: {_dataset: usage_shares, date, source_model_id, metric, share_percent}
    `source_model_id` is the gateway's display model name (e.g. "GLM 5.3");
    the reserved name "Other" is kept for identifiable-share reporting and is
    deliberately unmappable to any geography.
    """
    today = dt.date.today()
    window = days if days is not None else 60
    start = max(HIST_START, today - dt.timedelta(days=window - 1))
    end = min(today, dt.date(today.year, today.month, today.day))
    # request one window covering the range (API allows arbitrary ranges)
    payload = _fetch_range(start, end)
    rows_out: list[dict] = []
    seen_earliest = payload.get("earliest_available_date")
    for entry in payload.get("rows", []):
        name = entry.get("name")
        metric = entry.get("metric")
        share = entry.get("share_percent")
        date = entry.get("date")
        if not name or metric not in METRICS or share is None or not date:
            continue
        rows_out.append({
            "_dataset": "usage_shares",
            "date": date,
            "source_model_id": name,
            "metric": metric,
            "share_percent": float(share),
        })
    log.info("Vercel AI Gateway leaderboard %s..%s: %d rows (earliest available: %s)",
             start, end, len(rows_out), seen_earliest)
    return rows_out


def collect_labs(days: int | None = None) -> list[dict]:
    """Optional: lab (creator) shares. Creator slugs (deepseek, zai, ...)
    map cleanly to companies; useful as a cross-check of model-level mapping.
    Stored in the same usage_shares dataset with group-qualified ids.
    """
    today = dt.date.today()
    window = days if days is not None else 60
    start = max(HIST_START, today - dt.timedelta(days=window - 1))
    payload = http_get_json(EXPORT_URL, params={
        "dataset": "labs", "modality": "text", "format": "json",
        "from": start.isoformat(), "to": today.isoformat(),
    })
    archive_raw("vercel_gateway", payload,
                label=f"leaderboard_labs_{start}_{today}")
    rows_out: list[dict] = []
    for entry in payload.get("rows", []):
        if entry.get("metric") not in METRICS:
            continue
        rows_out.append({
            "_dataset": "usage_shares",
            "date": entry.get("date"),
            "source_model_id": f"lab:{entry.get('name')}",
            "metric": entry.get("metric"),
            "share_percent": float(entry.get("share_percent", 0.0)),
        })
    return rows_out
