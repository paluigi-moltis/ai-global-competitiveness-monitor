#!/usr/bin/env python3
"""collect.py - retrieve source data, archive raw responses, produce
standardised datasets.

    python collect.py                  # all sources
    python collect.py --source openrouter
    python collect.py --list

Each collector:
  1. fetches public API data (respecting rate limits / source terms),
  2. archives the raw response under data/raw/<source>/<date>/,
  3. writes standardised rows via common.standardise().

Collection is idempotent: re-running appends/overwrites by (date, id) keys
and never creates duplicate observations.

Phase 1 status: framework only. Collectors marked "implemented" fetch live
data; others raise NotImplementedError with a pointer to the planned source.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import setup_logging, RAW_DIR, PROCESSED_DIR, standardise, write_processed  # noqa: E402
from common import load_models, load_model_mapping  # noqa: E402
from common import resolve_with_unmatched, write_unmatched_review  # noqa: E402

log = logging.getLogger("collect")

ALL_SOURCES = [
    "openrouter", "epoch", "artificial_analysis", "huggingface",
    "modelscope", "arena", "ollama", "livebench", "livecodebench", "swebench",
]


def fetch_source(source: str, days: int | None) -> list[dict]:
    """Dispatch to the collector module. Returns standardised row dicts."""
    if source == "openrouter":
        from collectors.openrouter import collect
        return collect(days=days)
    if source == "epoch":
        from collectors.epoch import collect
        return collect()
    if source == "artificial_analysis":
        from collectors.artificial_analysis import collect
        return collect()
    if source == "huggingface":
        from collectors.huggingface import collect
        return collect()
    if source == "modelscope":
        from collectors.modelscope import collect
        return collect()
    if source == "arena":
        from collectors.arena import collect
        return collect()
    if source == "ollama":
        from collectors.ollama import collect
        return collect()
    if source == "livebench":
        from collectors.livebench import collect
        return collect()
    if source == "livecodebench":
        from collectors.livecodebench import collect
        return collect()
    if source == "swebench":
        from collectors.swebench import collect
        return collect()
    raise ValueError(f"Unknown source: {source}")


def run_source(source: str, days: int | None) -> bool:
    log.info("=== %s ===", source)
    try:
        rows = fetch_source(source, days)
    except NotImplementedError as exc:
        log.warning("SKIP %s: %s", source, exc)
        return False
    except Exception:  # noqa: BLE001 - one failing source must not stop the others
        log.exception("FAILED %s", source)
        return False
    if not rows:
        log.warning("No rows returned by %s", source)
        return False

    import pandas as pd
    df = pd.DataFrame(rows)
    dataset = df.attrs.get("dataset") or rows[0].get("_dataset", "usage")
    if "_dataset" in df.columns:
        df = df.drop(columns=["_dataset"])
    std = standardise(dataset, df, source=source)
    write_processed(dataset if dataset != "downloads" else f"downloads_{source}", std)
    log.info("%s: %d standardised %s rows", source, len(std), dataset)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=ALL_SOURCES, action="append",
                        help="collect only these sources (repeatable)")
    parser.add_argument("--days", type=int, default=None,
                        help="historical window in days where supported")
    parser.add_argument("--list", action="store_true", help="list sources and exit")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.list:
        for s in ALL_SOURCES:
            print(s)
        return 0

    sources = args.source or ALL_SOURCES
    results = {s: run_source(s, args.days) for s in sources}
    ok = sum(results.values())
    log.info("Collection finished: %d/%d sources OK", ok, len(sources))
    for s, r in results.items():
        if not r:
            log.warning("  stale/failed: %s", s)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
