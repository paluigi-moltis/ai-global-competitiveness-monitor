"""Adoption indicator tests: OpenRouter shares excluding 'other',
per-platform download shares, open-weight splits."""
from __future__ import annotations

import pytest
import pandas as pd

import common
from common.adoption import downloads_components, openrouter_components


def pytest_approx(x):
    return pytest.approx(x, rel=1e-9)


def _model_info() -> pd.DataFrame:
    rows = []
    pairs = [
        ("openrouter", "openai/gpt-5"),
        ("openrouter", "deepseek/deepseek-r1"),
        ("openrouter", "mistralai/mistral-large-2411"),
        ("huggingface", "deepseek-ai/DeepSeek-R1"),
        ("huggingface", "openai/gpt-oss-120b"),
        ("huggingface", "mistralai/Devstral-Small-2507"),
        ("modelscope", "deepseek-ai/DeepSeek-R1"),
        ("modelscope", "Qwen/Qwen3-235B-A22B"),
        ("modelscope", "openai/gpt-oss-120b"),
    ]
    for source, smid in pairs:
        m = common.lookup_model(source, smid)
        rows.append({"source": source, "source_model_id": smid,
                     "model_id": m.model_id, "geography": m.geography,
                     "weights_status": m.weights_status,
                     "company_id": m.company_id})
    return pd.DataFrame(rows)


def test_openrouter_shares_exclude_other(sandbox_with_data):
    usage = pd.read_parquet(sandbox_with_data / "data" / "processed" / "usage.parquet")
    comp = openrouter_components(usage, _model_info())
    toks = comp[comp["component_id"] == "or_tokens_share"]
    # identifiable total = 1000+600+400 = 2000 (the 250 'other' is excluded)
    assert toks[toks["geography"] == "US"]["value"].iloc[0] == pytest_approx(1000 / 2000)
    assert toks[toks["geography"] == "China"]["value"].iloc[0] == pytest_approx(600 / 2000)
    assert toks[toks["geography"] == "EU"]["value"].iloc[0] == pytest_approx(400 / 2000)
    # shares across geographies sum to 1 (identifiable traffic only)
    assert toks["value"].sum() == pytest_approx(1.0)


def test_openweight_usage_split(sandbox_with_data):
    usage = pd.read_parquet(sandbox_with_data / "data" / "processed" / "usage.parquet")
    comp = openrouter_components(usage, _model_info())
    open_toks = comp[comp["component_id"] == "or_tokens_open_share"]
    # open-weight share of *total identifiable traffic*: only deepseek-r1 is
    # open -> China 600/2000, US and EU 0
    assert open_toks[open_toks["geography"] == "China"]["value"].iloc[0] == pytest_approx(600 / 2000)
    assert open_toks[open_toks["geography"] == "US"]["value"].iloc[0] == pytest_approx(0.0)
    assert open_toks[open_toks["geography"] == "EU"]["value"].iloc[0] == pytest_approx(0.0)


def test_platform_shares_kept_separate(sandbox_with_data):
    info = _model_info()
    dl_hf = pd.read_parquet(
        sandbox_with_data / "data" / "processed" / "downloads_huggingface.parquet")
    hf = downloads_components(dl_hf, info, "huggingface")
    # HF: deepseek 500, gpt-oss 300, devstral 200 -> total 1000
    assert hf[hf["geography"] == "China"]["value"].iloc[0] == pytest_approx(0.5)
    assert hf[hf["geography"] == "US"]["value"].iloc[0] == pytest_approx(0.3)
    assert hf[hf["geography"] == "EU"]["value"].iloc[0] == pytest_approx(0.2)

    dl_ms = pd.read_parquet(
        sandbox_with_data / "data" / "processed" / "downloads_modelscope.parquet")
    ms = downloads_components(dl_ms, info, "modelscope")
    # ModelScope: deepseek 400, qwen 350, gpt-oss 100 -> total 850
    assert ms[ms["geography"] == "China"]["value"].iloc[0] == pytest_approx(750 / 850)
    assert ms[ms["geography"] == "US"]["value"].iloc[0] == pytest_approx(100 / 850)
    # platform separation: component ids differ, never summed
    assert set(hf["component_id"]) == {"hf_downloads_share"}
    assert set(ms["component_id"]) == {"modelscope_downloads_share"}
