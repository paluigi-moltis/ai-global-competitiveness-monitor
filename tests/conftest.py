"""Shared pytest fixtures: isolated repo root with synthetic test data."""
from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import pandas as pd
import pytest

import common


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch) -> Path:
    """Create a synthetic data sandbox: copies config/ into tmp_path, points
    common paths there, writes synthetic standardised datasets."""
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "data" / "processed").mkdir(parents=True)

    # copy real config (small, hand-maintained)
    real_root = Path(common.__file__).resolve().parents[1]
    for f in (real_root / "config").glob("*.csv"):
        shutil.copy(f, root / "config" / f.name)

    # generate a weights workbook in the sandbox (paths resolve via scripts.ROOT)
    import sys
    sys.path.insert(0, str(real_root))
    from scripts import build_weights_template
    orig_root = build_weights_template.ROOT
    build_weights_template.ROOT = root
    try:
        build_weights_template.main()
    finally:
        build_weights_template.ROOT = orig_root

    # repoint module constants and clear caches
    monkeypatch.setattr(common, "ROOT", root)
    monkeypatch.setattr(common, "CONFIG_DIR", root / "config")
    monkeypatch.setattr(common, "DATA_DIR", root / "data")
    monkeypatch.setattr(common, "RAW_DIR", root / "data" / "raw")
    monkeypatch.setattr(common, "PROCESSED_DIR", root / "data" / "processed")
    common.clear_config_cache()
    yield root
    common.clear_config_cache()


def _synthetic_benchmarks() -> pd.DataFrame:
    """Two benchmark dates, three models per source, mix of geographies."""
    d1 = dt.date(2026, 1, 1)
    d2 = dt.date(2026, 2, 1)
    rows = [
        # epoch benchmark panel: scores out of 100
        # top10/20 ranks: US best, China second, EU third
        (d1, "epoch", "mmlu-pro", "gpt-5", 89.0),
        (d1, "epoch", "mmlu-pro", "deepseek-r1", 84.0),
        (d1, "epoch", "mmlu-pro", "mistral-large-2411", 80.0),
        (d2, "epoch", "mmlu-pro", "gpt-5", 90.0),
        (d2, "epoch", "mmlu-pro", "deepseek-r1", 86.5),
        (d2, "epoch", "mmlu-pro", "mistral-large-2411", 81.0),
        # open-weight panel: China best among open weights
        (d1, "epoch", "gpqa-diamond", "deepseek-r1", 78.0),
        (d1, "epoch", "gpqa-diamond", "gpt-oss-120b", 76.0),
        (d1, "epoch", "gpqa-diamond", "glm-4-5", 75.0),
        (d2, "epoch", "gpqa-diamond", "deepseek-r1", 80.0),
        (d2, "epoch", "gpqa-diamond", "gpt-oss-120b", 79.0),
        (d2, "epoch", "gpqa-diamond", "glm-4-5", 76.0),
    ]
    return pd.DataFrame(rows, columns=["date", "source", "benchmark",
                                       "source_model_id", "score"])


def _synthetic_usage() -> pd.DataFrame:
    d = dt.date(2026, 2, 1)
    rows = [
        (d, "openrouter", "openai/gpt-5", 1000.0),
        (d, "openrouter", "deepseek/deepseek-r1", 600.0),
        (d, "openrouter", "mistralai/mistral-large-2411", 400.0),
        # unattributable "other" bucket: excluded from geo shares
        (d, "openrouter", "other", 250.0),
    ]
    return pd.DataFrame(rows, columns=["date", "source", "source_model_id", "tokens"])


def _synthetic_downloads(platform: str, pairs: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [(dt.date(2026, 2, 1), platform, smid, v) for smid, v in pairs],
        columns=["date", "source", "source_model_id", "downloads"],
    )


@pytest.fixture()
def sandbox_with_data(sandbox: Path) -> Path:
    common.write_processed("benchmarks", _synthetic_benchmarks())
    common.write_processed("usage", _synthetic_usage())
    common.write_processed("downloads_huggingface", _synthetic_downloads(
        "huggingface",
        [("deepseek-ai/DeepSeek-R1", 500.0), ("openai/gpt-oss-120b", 300.0),
         ("mistralai/Devstral-Small-2507", 200.0)]))
    common.write_processed("downloads_modelscope", _synthetic_downloads(
        "modelscope",
        [("deepseek-ai/DeepSeek-R1", 400.0), ("Qwen/Qwen3-235B-A22B", 350.0),
         ("openai/gpt-oss-120b", 100.0)]))
    return sandbox
