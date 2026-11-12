"""Hugging Face collector - model metadata and download levels.

API: https://huggingface.co/api/models/<repo_id> (public, no auth; an
optional HF_TOKEN in .env only raises rate limits - see .env.example).

Data notes (spec §7):
- `downloads` on the HF API is a CUMULATIVE ROLLING 30-DAY counter, NOT a
  daily increment. This collector stores levels only; conversion to daily
  changes must happen in processing with explicit documentation, never here.
- Only open-weight repos make sense to track (downloads of gated/closed
  repos are not comparable); repos are configured per canonical model via
  HF_REPOS below (repo_id -> canonical model_id in models.csv).
- `createdAt` is the repo creation date, used as release_date.
"""
from __future__ import annotations

import logging
import os

from collectors.base import archive_raw, http_get_json

log = logging.getLogger("huggingface")

API = "https://huggingface.co/api/models"

# canonical model_id -> HF repo_id (config-driven; extend as models are added)
HF_REPOS: dict[str, str] = {
    "gpt-oss-120b": "openai/gpt-oss-120b",
    "gpt-oss-20b": "openai/gpt-oss-20b",
    "llama-4-maverick": "meta-llama/Llama-4-Maverick-17B-128E-Instruct",
    "llama-4-scout": "meta-llama/Llama-4-Scout-17B-16E-Instruct",
    "llama-3-3-70b": "meta-llama/Llama-3.3-70B-Instruct",
    "deepseek-v3-1": "deepseek-ai/DeepSeek-V3.1",
    "deepseek-r1": "deepseek-ai/DeepSeek-R1",
    "qwen3-235b": "Qwen/Qwen3-235B-A22B",
    "qwen3-32b": "Qwen/Qwen3-32B",
    "qwen2-5-72b": "Qwen/Qwen2.5-72B-Instruct",
    "glm-4-5": "zai-org/GLM-4.5",
    "glm-4-6": "zai-org/GLM-4.6",
    "kimi-k2": "moonshotai/Kimi-K2-Instruct",
    "minimax-m1": "MiniMaxAI/MiniMax-M1-80k",
    "mistral-large-2411": "mistralai/Mistral-Large-2411",
}


def collect(days: int | None = None) -> list[dict]:
    """Snapshot download levels + metadata for configured repos.

    Emits two datasets (returned together; collect.py splits by _dataset):
    - downloads rows: {date, source_model_id, downloads}
    - model_metadata rows: {date, source_model_id, company_name,
      weights_status, release_date}
    source_model_id is the HF repo_id.
    """
    import datetime as dt

    headers = {"User-Agent": "ai-monitor/0.1"}
    token = os.environ.get("HF_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    today = dt.date.today().isoformat()
    out: list[dict] = []
    for model_id, repo_id in HF_REPOS.items():
        try:
            data = http_get_json(f"{API}/{repo_id}", headers=headers)
        except RuntimeError as exc:
            log.warning("huggingface: %s failed: %s", repo_id, exc)
            continue
        archive_raw("huggingface", data, label=repo_id.replace("/", "_"))
        downloads = data.get("downloads")
        created = (data.get("createdAt") or "")[:10] or None
        out.append({
            "_dataset": "downloads",
            "date": today,
            "source_model_id": repo_id,
            "downloads": float(downloads) if downloads is not None else None,
        })
        out.append({
            "_dataset": "model_metadata",
            "date": today,
            "source_model_id": repo_id,
            "company_name": repo_id.split("/")[0],
            "weights_status": "open",
            "release_date": created,
        })
        log.info("huggingface: %s downloads=%s created=%s", repo_id,
                 downloads, created)
    return [r for r in out if r.get("downloads") is not None
            or r["_dataset"] == "model_metadata"]
