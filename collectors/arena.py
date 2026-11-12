"""LMArena collector - human-preference rankings and historical scores.

Leaderboard: https://lmarena.ai (public leaderboard; historical Elo by
release date available via their data releases). Phase 2: verify current
endpoint/API before implementing. Planned output: benchmarks rows for
benchmark 'lmarena'.
"""
from __future__ import annotations

import logging

log = logging.getLogger("arena")


def collect() -> list[dict]:
    raise NotImplementedError(
        "LMArena collector lands in Phase 2 after verifying current "
        "leaderboard access (site/API have changed repeatedly)."
    )
