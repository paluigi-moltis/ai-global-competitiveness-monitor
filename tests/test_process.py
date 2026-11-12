"""Standardisation and process.py end-to-end tests on synthetic data."""
from __future__ import annotations

import pandas as pd

import common
from common import standardise


def test_standardise_usage_schema():
    df = pd.DataFrame([
        {"date": "2026-02-01", "source_model_id": "openai/gpt-5", "tokens": "1234"},
        {"date": "2026-02-01", "source_model_id": "x", "tokens": None},
    ])
    std = standardise("usage", df, source="openrouter")
    assert list(std.columns) == ["date", "source", "source_model_id", "tokens", "estimated_spend"]
    assert std["tokens"].dtype == "float64"
    assert std["estimated_spend"].isna().all()
    assert (std["source"] == "openrouter").all()


def test_standardise_benchmarks_schema():
    df = pd.DataFrame([
        {"date": "2026-02-01", "benchmark": "mmlu-pro", "source_model_id": "gpt-5", "score": "89.5"},
    ])
    std = standardise("benchmarks", df)
    assert list(std.columns) == ["date", "benchmark", "source", "source_model_id", "score", "rank"]
    assert std["score"].iloc[0] == 89.5


def _repoint(monkeypatch, sandbox):
    """Point the `common` module at the sandbox repo (process.py reads common.*)."""
    import common as common_mod
    monkeypatch.setattr(common_mod, "ROOT", sandbox)
    monkeypatch.setattr(common_mod, "CONFIG_DIR", sandbox / "config")
    monkeypatch.setattr(common_mod, "DATA_DIR", sandbox / "data")
    monkeypatch.setattr(common_mod, "RAW_DIR", sandbox / "data" / "raw")
    monkeypatch.setattr(common_mod, "PROCESSED_DIR", sandbox / "data" / "processed")
    common_mod.clear_config_cache()


def test_process_end_to_end(sandbox_with_data, monkeypatch):
    """Run process.py main() in the sandbox and verify outputs."""
    _repoint(monkeypatch, sandbox_with_data)
    import process
    rc = process.main([])
    assert rc == 0
    proc = sandbox_with_data / "data" / "processed"
    for name in ("benchmark_observations", "ranked_benchmarks",
                 "capability_components", "capability_detail",
                 "adoption_components", "models_ref"):
        assert (proc / f"{name}.parquet").exists(), name

    obs = pd.read_parquet(proc / "benchmark_observations.parquet")
    assert set(obs["geography"]) <= {"US", "China", "EU", "RoW"}
    assert (obs["company_name"] != "").all()

    adoption = pd.read_parquet(proc / "adoption_components.parquet")
    comp_ids = set(adoption["component_id"])
    assert {"or_tokens_share", "or_tokens_open_share",
            "hf_downloads_share", "modelscope_downloads_share"} <= comp_ids

    idx = pd.read_parquet(proc / "index_daily.parquet")
    assert not idx.empty
    assert set(idx["category"]) == {"capability", "adoption"}
    assert set(idx["geography"]).issubset({"US", "China", "EU", "RoW"})
    assert idx["index"].between(0, 1).all()
    # no look-ahead: index dates start no earlier than first observation month
    assert idx["date"].min() >= pd.Timestamp("2026-01-01") - pd.Timedelta(days=1)


def test_weight_change_requires_no_recollection(sandbox_with_data, monkeypatch):
    """Editing weights.xlsx and rerunning process.py changes index values
    without touching collected data."""
    import openpyxl
    _repoint(monkeypatch, sandbox_with_data)
    import process
    assert process.main([]) == 0
    proc = sandbox_with_data / "data" / "processed"

    # generate a real weights workbook in the sandbox and rerun
    import sys
    from scripts import build_weights_template
    monkeypatch.setattr(build_weights_template, "ROOT", sandbox_with_data)
    build_weights_template.main()
    idx_before = pd.read_parquet(proc / "index_daily.parquet")

    wb = openpyxl.load_workbook(sandbox_with_data / "config" / "weights.xlsx")
    ws = wb["Weights"]
    headers = [c.value for c in ws[1]]
    comp_col = headers.index("component_id") + 1
    w_col = headers.index("weight") + 1
    changed = 0
    for row in ws.iter_rows(min_row=2):
        comp = row[comp_col - 1].value
        if comp == "or_tokens_share":
            row[w_col - 1].value = 5.0  # was 1.0
            changed += 1
    assert changed == 1
    wb.save(sandbox_with_data / "config" / "weights.xlsx")

    assert process.main([]) == 0
    idx_after = pd.read_parquet(proc / "index_daily.parquet")
    a_before = idx_before[(idx_before["category"] == "adoption")
                          & (idx_before["geography"] == "US")]["index"].iloc[-1]
    a_after = idx_after[(idx_after["category"] == "adoption")
                        & (idx_after["geography"] == "US")]["index"].iloc[-1]
    assert a_before != a_after
