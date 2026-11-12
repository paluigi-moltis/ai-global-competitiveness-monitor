"""Ollama collector - model catalogue and download indicators.

Public library page lists models; pulls counts are shown for some models.
Verify counter semantics before treating pulls as a comparable metric.
"""
from __future__ import annotations

import logging

log = logging.getLogger("ollama")


def collect() -> list[dict]:
    raise NotImplementedError(
        "Ollama collector lands in Phase 2+ after verifying public pull "
        "count availability and semantics."
    )
