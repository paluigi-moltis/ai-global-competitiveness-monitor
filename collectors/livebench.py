"""LiveBench collector - benchmark scores from official leaderboard CSVs.

The LiveBench leaderboard site (livebench.github.io, repo
LiveBench/livebench.github.io) publishes one CSV per release in
public/table_<release>.csv plus public/categories_<release>.json listing
the task columns per category. Releases carry the release date in the
filename (e.g. table_2026_06_25.csv) - collecting all releases gives the
full historical series, which we store as separate dated observations
(no snapshot replacement).

LiveBench 2.0 (release 2026-06-25) restructured task names vs 1.0; the
overall score is computed as the mean of ALL task columns (each 0-100),
matching the site's own averaging, and is stored 0-1. Task-mix changes
between releases are a documented caveat: cross-release comparability is
approximate around 2026-06-25.
"""
from __future__ import annotations

import csv
import io
import logging

from collectors.base import archive_raw, http_get_json

log = logging.getLogger("livebench")

SITE = "https://raw.githubusercontent.com/LiveBench/livebench.github.io/main/public"


def _list_releases() -> list[str]:
    """Release dates (YYYY_MM_DD) discovered from categories_<release>.json
    files in the site repo."""
    tree = http_get_json(
        "https://api.github.com/repos/LiveBench/livebench.github.io/"
        "git/trees/main?recursive=1")
    releases = []
    for t in tree.get("tree", []):
        name = t["path"].rsplit("/", 1)[-1]
        if name.startswith("table_") and name.endswith(".csv"):
            releases.append(name[len("table_"):-len(".csv")])
    return sorted(releases)


def _release_rows(release: str) -> list[dict]:
    import requests

    resp = requests.get(f"{SITE}/table_{release}.csv", timeout=60,
                        headers={"User-Agent": "ai-monitor/0.1"})
    resp.raise_for_status()
    archive_raw("livebench", None, label=f"table_{release}",
                content=resp.content, ext="csv")
    return list(csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig"))))


def collect(days: int | None = None) -> list[dict]:
    """Emit benchmark observations for every historical release.

    Rows: {_dataset: benchmarks, date, benchmark=livebench,
    source_model_id, score} with score = mean of all task columns / 100.
    `date` is the release date.
    """
    rows: list[dict] = []
    for release in _list_releases():
        table = _release_rows(release)
        if not table:
            continue
        date = f"{release[:4]}-{release[5:7]}-{release[8:10]}"
        before = len(rows)
        for r in table:
            model = (r.get("model") or "").strip()
            if not model:
                continue
            scores = []
            for k, v in r.items():
                if k == "model" or v in ("", None):
                    continue
                try:
                    scores.append(float(v))
                except ValueError:
                    continue
            if not scores:
                continue
            rows.append({
                "_dataset": "benchmarks",
                "date": date,
                "benchmark": "livebench",
                "source_model_id": model,
                "score": sum(scores) / len(scores) / 100.0,
            })
        log.info("livebench: release %s -> %d models", release,
                 len(rows) - before)
    return rows
