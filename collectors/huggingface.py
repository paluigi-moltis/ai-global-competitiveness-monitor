"""Hugging Face collector - model metadata and downloads.

API: https://huggingface.co/api/models/<repo_id> -> ?downloads=<cumulative>
Data notes (spec §7):
- `downloads` is a CUMULATIVE rolling counter (last 30 days), NOT a daily
  increment. This collector stores levels; conversion to daily changes must
  happen in processing with explicit documentation, never here.
- Only open-weight repos tracked (downloads are meaningless for closed models).
"""
from __future__ import annotations

import logging

log = logging.getLogger("huggingface")

API = "https://huggingface.co/api/models"


def collect() -> list[dict]:
    raise NotImplementedError(
        "Hugging Face collector lands in Phase 2 (list models + downloads "
        "levels for mapped open-weight repos)."
    )
