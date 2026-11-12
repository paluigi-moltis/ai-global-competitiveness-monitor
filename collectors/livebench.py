"""LiveBench collector - benchmark scores.

https://livebench.ai - results published on GitHub (monthly refreshes,
contamination-free). Phase 2: use the official results repo/CSV releases.
"""
from __future__ import annotations

import logging

log = logging.getLogger("livebench")


def collect() -> list[dict]:
    raise NotImplementedError(
        "LiveBench collector lands in Phase 2 (GitHub results releases)."
    )
