"""ModelScope collector - model metadata and downloads (Chinese platform)."""
from __future__ import annotations

import logging

log = logging.getLogger("modelscope")


def collect() -> list[dict]:
    raise NotImplementedError(
        "ModelScope collector lands in Phase 2+ after verifying the public "
        "API and download-counter semantics."
    )
