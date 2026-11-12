"""SWE-bench collector - software engineering benchmark scores.

Use SWE-bench Verified results only (leaderboard:
https://www.swebench.com). Phase 2: verify leaderboard data export.
"""
from __future__ import annotations

import logging

log = logging.getLogger("swebench")


def collect() -> list[dict]:
    raise NotImplementedError(
        "SWE-bench collector lands in Phase 2 (leaderboard export; "
        "Verified subset only)."
    )
