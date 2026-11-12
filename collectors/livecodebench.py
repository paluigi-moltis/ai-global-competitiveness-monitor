"""LiveCodeBench collector - coding benchmark scores.

https://livecodebench.github.io - problem releases with published model
results. Phase 2: verify current results export format.
"""
from __future__ import annotations

import logging

log = logging.getLogger("livecodebench")


def collect() -> list[dict]:
    raise NotImplementedError(
        "LiveCodeBench collector lands in Phase 2 (results exports)."
    )
