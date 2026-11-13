"""Arena (LMArena) collector - human-preference rankings, full history.

Source: the official Arena Leaderboard Dataset on Hugging Face,
https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset
(announced 2026-04-02, arena.ai/blog/arena-leaderboard-dataset; CC BY 4.0;
NOT gated - anonymous parquet download works).

This replaces the earlier plan of scraping lmarena.ai, whose API rejects
unauthenticated clients (HTTP 403, verified 2026-11-12). The dataset
contains the complete history of every published leaderboard:

- subsets/configs per arena: text, vision, search, document, webdev,
  text_to_image, image_edit, text_to_video, image_to_video, video_edit,
  plus style-controlled and agent-signal variants (23 total)
- splits per subset: latest (most recent publish) and full (all history)
- columns: model_name, organization, license, rating (Bradley-Terry),
  rating_lower/upper, variance, vote_count, rank, category,
  leaderboard_publish_date

We ingest the text arena (overall category) as benchmark 'lmarena' per
config/benchmarks.csv. date = leaderboard_publish_date: a dated, public
observation set (the release the rating was computed in), matching our
true-vintage convention. Rating is normalised by 1400 to a 0-1 scale:
1.0 ~= 1400 Elo, comfortably above the historical frontier (max observed
2026-11: ~1538; 2023 floor: ~1000).

The text/full parquet (~1.3M rows incl. per-category snapshots) is
archived raw; only overall-category rows are emitted.
"""
from __future__ import annotations

import io
import logging

from collectors.base import archive_raw

log = logging.getLogger("arena")

DATASET_URL = ("https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset"
               "/resolve/main/text/full-00000-of-00001.parquet")
BENCHMARK_ID = "lmarena"
RATING_SCALE = 1400.0  # rating / RATING_SCALE -> 0-1 score
CATEGORIES = {"overall", "overall_with_style_control"}


def collect(days: int | None = None) -> list[dict]:
    """Download the Arena leaderboard dataset and emit benchmark rows.

    Rows: {_dataset: benchmarks, date, benchmark, source_model_id, score}
    with date = leaderboard_publish_date (ISO). One observation per
    (publish date, model) from the overall text-arena categories.
    """
    import pandas as pd
    import requests

    resp = requests.get(DATASET_URL, timeout=300,
                        headers={"User-Agent": "ai-monitor/0.1"})
    resp.raise_for_status()
    archive_raw("arena", None, label="leaderboard_text_full",
                content=resp.content, ext="parquet")

    df = pd.read_parquet(io.BytesIO(resp.content),
                         columns=["model_name", "rating", "category",
                                  "leaderboard_publish_date"])
    df = df[df["category"].isin(CATEGORIES)]
    df = df.dropna(subset=["model_name", "rating", "leaderboard_publish_date"])
    df["leaderboard_publish_date"] = (
        df["leaderboard_publish_date"].astype(str).str.slice(0, 10))
    df = df.drop_duplicates(
        subset=["leaderboard_publish_date", "model_name"], keep="last")

    rows = [
        {
            "_dataset": "benchmarks",
            "date": r.leaderboard_publish_date,
            "benchmark": BENCHMARK_ID,
            "source_model_id": r.model_name,
            "score": float(r.rating) / RATING_SCALE,
        }
        for r in df.itertuples()
    ]
    log.info("arena: %d text-arena overall observations", len(rows))
    return rows
