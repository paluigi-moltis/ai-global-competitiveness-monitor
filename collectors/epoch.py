"""Epoch AI collector - model and benchmark information.

Primary endpoint: https://data.epoch.ai/data/machine_learning_benchmark_data.csv
(Comprehensive benchmark results with model, benchmark, score and date columns.)

Data notes:
- Verify the exact export URL against https://epoch.ai/data before relying
  on it in production; Epoch changes exports occasionally.
- Score definitions vary per benchmark; keep the benchmark column as the
  source_model_id namespace and map benchmarks via config/benchmarks.csv.
"""
from __future__ import annotations

import io
import logging

import pandas as pd

from collectors.base import archive_raw, http_get_json

log = logging.getLogger("epoch")

EXPORT_URL = "https://data.epoch.ai/data/machine_learning_benchmark_data.csv"


def collect() -> list[dict]:
    raise NotImplementedError(
        "Epoch AI collector lands in Phase 2 after verifying the current export "
        "URL and column names at https://epoch.ai/data. Planned output: "
        "benchmarks rows (date, benchmark, source_model_id, score, rank)."
    )
