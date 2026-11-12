"""Epoch AI collector - benchmark results + model metadata.

Source: https://epoch.ai/data/benchmark_data.zip (free download, CC BY 4.0,
no authentication). The zip contains one CSV per benchmark: internal Epoch
runs use columns [Model version, mean_score, Best score (across scorers),
Release date, Organization, Country, ...]; external runs have per-benchmark
score columns declared in benchmark_metadata.csv inside the zip.

We ingest only the benchmarks configured in config/benchmarks.csv with
preferred_source=epoch (see EPOCH_BENCHMARKS below for the zip-file
mapping). Score = mean_score (internal) or the metadata-declared score
column (external), normalised by the declared scale so all scores are 0-1.
The zip is archived raw; extraction is repeatable offline.

AIME note: Epoch evaluates models on OTIS Mock AIME 2024-2025 (a fixed
competition-math proxy); config/benchmarks.csv documents this choice.
"""
from __future__ import annotations

import datetime as dt
import io
import logging
import zipfile

from collectors.base import archive_raw

log = logging.getLogger("epoch")

BENCHMARK_ZIP_URL = "https://epoch.ai/data/benchmark_data.zip"
MODELS_CSV_URL = "https://epoch.ai/data/all_ai_models.csv"

# benchmark_id (config/benchmarks.csv) -> (zip member, score column, scale)
# score column None => internal-runs CSV (use mean_score).
EPOCH_BENCHMARKS: dict[str, tuple[str, str | None, float]] = {
    "gpqa-diamond": ("gpqa_diamond.csv", None, 1.0),
    "math": ("math_level_5.csv", None, 1.0),
    "aime": ("otis_mock_aime_2024_2025.csv", None, 1.0),
    "swebench": ("swe_bench_verified.csv", None, 1.0),
}

INTERNAL_SCORE_COL = "mean_score"


def _parse_date(s: str) -> str | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        for fmt in ("%d/%m/%Y", "%m/%d/%Y"):
            try:
                return dt.datetime.strptime(s, fmt).date().isoformat()
            except ValueError:
                continue
    return None


def collect(days: int | None = None) -> list[dict]:
    """Download the Epoch benchmark zip and emit benchmark observation rows.

    Rows: {_dataset: benchmarks, date, benchmark, source_model_id, score}
    `date` is the model release date carried by Epoch (their evaluation runs
    are not dated per-row); `source_model_id` is Epoch's "Model version".
    Scores are normalised to 0-1 using the declared scale.
    """
    import csv as _csv

    import requests

    resp = requests.get(BENCHMARK_ZIP_URL, timeout=180,
                        headers={"User-Agent": "ai-monitor/0.1"})
    resp.raise_for_status()
    archive_raw("epoch", None, label="benchmark_data",
                content=resp.content, ext="zip")
    zf = zipfile.ZipFile(io.BytesIO(resp.content))

    rows: list[dict] = []
    for bench_id, (member, score_col, scale) in EPOCH_BENCHMARKS.items():
        try:
            text = zf.read(member).decode("utf-8-sig")
        except KeyError:
            log.warning("epoch: %s missing from zip (renamed upstream?)", member)
            continue
        before = len(rows)
        for r in _csv.DictReader(io.StringIO(text)):
            model = (r.get("Model version") or "").strip()
            raw = r.get(score_col or INTERNAL_SCORE_COL, "")
            date = _parse_date(r.get("Release date", ""))
            if not model or raw in ("", None) or not date:
                continue
            try:
                score = float(raw) / scale
            except ValueError:
                continue
            rows.append({
                "_dataset": "benchmarks",
                "date": date,
                "benchmark": bench_id,
                "source_model_id": model,
                "score": score,
            })
        log.info("epoch: %s -> %d observations", bench_id, len(rows) - before)
    return rows


def collect_models() -> list[dict]:
    """Optional: model metadata from Epoch's all_ai_models.csv (release
    dates, organization). Emits model_metadata rows for cross-checking
    config/models.csv.
    """
    import csv as _csv

    import requests

    resp = requests.get(MODELS_CSV_URL, timeout=180,
                        headers={"User-Agent": "ai-monitor/0.1"})
    resp.raise_for_status()
    archive_raw("epoch", None, label="all_ai_models", content=resp.content,
                ext="csv")
    rows: list[dict] = []
    for r in _csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig"))):
        model = (r.get("Model") or "").strip()
        date = _parse_date(r.get("Release date", ""))
        if not model or not date:
            continue
        rows.append({
            "_dataset": "model_metadata",
            "date": date,
            "source_model_id": model,
            "company_name": (r.get("Organization") or "").strip(),
            "weights_status": "unknown",
            "release_date": date,
        })
    log.info("epoch: %d model metadata rows", len(rows))
    return rows
