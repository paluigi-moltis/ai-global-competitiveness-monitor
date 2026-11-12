"""ModelScope collector - download levels for configured repos (CN platform).

API: GET https://modelscope.cn/api/v1/models/<namespace>/<name> (public,
no auth). Returns JSON with Data.Downloads (cumulative counter) and
Data.Stars.

Data notes (spec §7):
- ModelScope exposes NO public list/search API (list endpoints return 404
  without auth), so repos are configured explicitly below, mirroring the
  Hugging Face repo choices.
- The semantics of `Downloads` (window, increment vs cumulative) are NOT
  officially documented. Levels are stored; no daily changes are derived.
- Shares are computed within this platform only and never summed with other
  platforms' counters.
"""
from __future__ import annotations

import datetime as dt
import logging

from collectors.base import archive_raw, http_get_json

log = logging.getLogger("modelscope")

API = "https://modelscope.cn/api/v1/models"

# canonical model_id -> ModelScope repo (namespace/name); config-driven
MODELSCOPE_REPOS: dict[str, str] = {
    "deepseek-v3-1": "deepseek-ai/DeepSeek-V3.1",
    "deepseek-r1": "deepseek-ai/DeepSeek-R1",
    "glm-4-5": "ZhipuAI/GLM-4.5",
    "glm-4-6": "ZhipuAI/GLM-4.6",
    "kimi-k2": "moonshotai/Kimi-K2-Instruct",
    "qwen3-235b": "Qwen/Qwen3-235B-A22B",
    "qwen3-32b": "Qwen/Qwen3-32B",
}


def collect(days: int | None = None) -> list[dict]:
    """Snapshot Downloads levels for configured repos.

    Rows: {_dataset: downloads, date, source_model_id, downloads}
    source_model_id is the ModelScope repo id (namespace/name).
    """
    today = dt.date.today().isoformat()
    out: list[dict] = []
    for model_id, repo in MODELSCOPE_REPOS.items():
        try:
            data = http_get_json(f"{API}/{repo}")
        except RuntimeError as exc:
            log.warning("modelscope: %s failed: %s", repo, exc)
            continue
        payload = data.get("Data") or {}
        downloads = payload.get("Downloads")
        archive_raw("modelscope", data, label=repo.replace("/", "_"))
        if downloads is None:
            log.warning("modelscope: %s has no Downloads field", repo)
            continue
        out.append({
            "_dataset": "downloads",
            "date": today,
            "source_model_id": repo,
            "downloads": float(downloads),
        })
        log.info("modelscope: %s downloads=%s", repo, downloads)
    return out
