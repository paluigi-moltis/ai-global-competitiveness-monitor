"""Ollama collector - download levels from the public library pages.

The registry API (registry.ollama.ai/v2/...) serves manifests but NO usage
statistics. Download counts appear only in the HTML of
https://ollama.com/library/<model> as "<N>M Downloads" per tag page.

Data notes (spec §7):
- Counter semantics are undocumented (cumulative vs rolling window unknown).
  Levels are stored; no daily changes are derived.
- HTML scraping is the only public access path; kept tolerant (a missing
  count yields no row, never a fabricated value) and clearly documented.
"""
from __future__ import annotations

import datetime as dt
import logging
import re

from collectors.base import archive_raw

log = logging.getLogger("ollama")

LIBRARY_URL = "https://ollama.com/library/{tag}"

# canonical model_id -> ollama library tag; config-driven
OLLAMA_TAGS: dict[str, str] = {
    "gpt-oss-120b": "gpt-oss:120b",
    "gpt-oss-20b": "gpt-oss:20b",
    "llama-3-3-70b": "llama3.3",
    "llama-4-maverick": "llama4:maverick",
    "llama-4-scout": "llama4:scout",
    "deepseek-r1": "deepseek-r1",
    "deepseek-v3-1": "deepseek-v3.1",
    "qwen3-235b": "qwen3:235b",
    "glm-4-6": "glm4.6",
    "kimi-k2": "kimi-k2",
}

_COUNT_RE = re.compile(r">\s*([\d.,]+[MBK]?)\s*</span>\s*<span[^>]*>\s*&nbsp;Downloads")


def _parse_count(text: str) -> float | None:
    """'14.9M' -> 14_900_000; '812K' -> 812_000; '1.2B' -> 1_200_000_000."""
    m = re.match(r"([\d.,]+)\s*([MBK]?)", text.strip().upper())
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    mult = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2)]
    return value * mult


def collect(days: int | None = None) -> list[dict]:
    """Snapshot download counts from library pages.

    Rows: {_dataset: downloads, date, source_model_id, downloads}
    source_model_id is the ollama tag (e.g. 'gpt-oss:120b').
    """
    import requests

    today = dt.date.today().isoformat()
    out: list[dict] = []
    for model_id, tag in OLLAMA_TAGS.items():
        url = LIBRARY_URL.format(tag=tag)
        try:
            resp = requests.get(url, timeout=30,
                                headers={"User-Agent": "Mozilla/5.0 ai-monitor/0.1"})
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.warning("ollama: %s fetch failed: %s", tag, exc)
            continue
        archive_raw("ollama", None, label=tag.replace(":", "_"),
                    content=resp.content, ext="html")
        m = _COUNT_RE.search(resp.text)
        if not m:
            log.warning("ollama: no Downloads figure found on %s", url)
            continue
        count = _parse_count(m.group(1))
        if count is None:
            continue
        out.append({
            "_dataset": "downloads",
            "date": today,
            "source_model_id": tag,
            "downloads": count,
        })
        log.info("ollama: %s downloads=%.0f (parsed from '%s')", tag, count,
                 m.group(1))
    return out
