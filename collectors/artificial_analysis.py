"""Artificial Analysis collector - model evaluations and rankings.

API: https://artificialanalysis.ai/api (API key required for some endpoints;
check current terms). Phase 2: verify free endpoints vs key requirement,
then implement. Planned output: benchmarks rows.
"""
from __future__ import annotations

import logging

log = logging.getLogger("artificial_analysis")


def collect() -> list[dict]:
    raise NotImplementedError(
        "Artificial Analysis collector lands in Phase 2 after verifying API "
        "access conditions (some endpoints need a key)."
    )
