"""Index calculation tests: weight normalisation, missing-component
handling, coverage, carry-forward without look-ahead, negative weights."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from common.indices import WeightConfigError, asof_components, composite_index, load_weights


def _weights_df(pairs: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [(c, w, "", "") for c, w in pairs],
        columns=["component_id", "weight", "description", "category"],
    ).set_index("component_id")


def test_weights_normalisation_and_missing_components():
    w = _weights_df([("a", 2.0), ("b", 1.0), ("c", 1.0)])
    comps = pd.DataFrame([
        # geo US has all three: (0.6*2 + 0.5*1 + 0.2*1)/4 = 0.475
        ("2026-01-01", "a", "US", 0.6),
        ("2026-01-01", "b", "US", 0.5),
        ("2026-01-01", "c", "US", 0.2),
        # geo EU lacks 'b': (0.4*2 + 0.1*1)/3 = 0.3  (renormalised, b NOT zero)
        ("2026-01-01", "a", "EU", 0.4),
        ("2026-01-01", "c", "EU", 0.1),
    ], columns=["date", "component_id", "geography", "value"])
    idx = composite_index(comps, w)
    us = idx[idx["geography"] == "US"].iloc[0]
    eu = idx[idx["geography"] == "EU"].iloc[0]
    assert us["index"] == pytest.approx(0.475)
    assert eu["index"] == pytest.approx(0.3)
    # coverage: EU has 3 of 4 total weight
    assert us["coverage"] == pytest.approx(1.0)
    assert eu["coverage"] == pytest.approx(0.75)


def test_zero_weight_component_excluded():
    w = _weights_df([("a", 2.0), ("b", 0.0)])
    comps = pd.DataFrame([
        ("2026-01-01", "a", "US", 0.5),
        ("2026-01-01", "b", "US", 0.9),  # zero-weight -> ignored entirely
    ], columns=["date", "component_id", "geography", "value"])
    idx = composite_index(comps, w)
    assert idx.iloc[0]["index"] == pytest.approx(0.5)
    assert idx.iloc[0]["coverage"] == pytest.approx(1.0)


def test_negative_weights_rejected():
    w = _weights_df([("a", -1.0)])
    with pytest.raises(WeightConfigError):
        # load_weights validates; composite_index also guards via w>0 filter
        composite_index(pd.DataFrame(
            [("2026-01-01", "a", "US", 1.0)],
            columns=["date", "component_id", "geography", "value"]), w)


def test_asof_no_look_ahead():
    comps = pd.DataFrame([
        (dt.date(2026, 1, 1), "a", "US", 0.2),
        (dt.date(2026, 2, 1), "a", "US", 0.8),
    ], columns=["date", "component_id", "geography", "value"])
    dates = pd.date_range("2026-01-15", "2026-02-15", freq="D")
    asof = asof_components(comps, dates)
    jan = asof[asof["date"] == pd.Timestamp("2026-01-20")].iloc[0]
    feb = asof[asof["date"] == pd.Timestamp("2026-02-10")].iloc[0]
    assert jan["value"] == pytest.approx(0.2)   # carries Jan obs forward
    assert feb["value"] == pytest.approx(0.8)   # Feb obs visible only in Feb
    # freshness retained
    assert jan["obs_date"] == pd.Timestamp("2026-01-01")
    assert feb["obs_date"] == pd.Timestamp("2026-02-01")
    # nothing before first observation
    assert asof["date"].min() >= pd.Timestamp("2026-01-01")

def test_real_weights_template_loads():
    """The generated weights.xlsx must load and cover capability + adoption."""
    from pathlib import Path
    from scripts.build_weights_template import build_rows
    rows = build_rows(Path(__file__).resolve().parents[1] / "config" / "benchmarks.csv")
    w = pd.DataFrame(rows).set_index("component_id")
    assert (w["weight"] >= 0).all()
    assert "cap_mmlu-pro_best_open" in w.index
    assert "cap_ceval_best" in w.index          # Chinese benchmarks included
    assert "or_tokens_share" in w.index
    assert "hf_downloads_share" in w.index
    # estimated spending is experimental -> zero default weight
    assert w.loc["or_spend_share", "weight"] == 0.0


def test_index_end_to_end_with_template_weights():
    from pathlib import Path
    from scripts.build_weights_template import build_rows
    rows = build_rows(Path(__file__).resolve().parents[1] / "config" / "benchmarks.csv")
    w = pd.DataFrame(rows)[["component_id", "weight", "description", "category"]].set_index("component_id")
    comps = pd.DataFrame([
        ("2026-01-01", "cap_mmlu-pro_best", "US", 1.0),
        ("2026-01-01", "cap_mmlu-pro_best", "China", 0.5),
        ("2026-01-01", "or_tokens_share", "US", 0.5),
        ("2026-01-01", "or_tokens_share", "China", 0.3),
    ], columns=["date", "component_id", "geography", "value"])
    idx = composite_index(comps, w)
    us = idx[idx["geography"] == "US"].iloc[0]
    assert 0 <= us["index"] <= 1
    assert us["coverage"] < 1.0  # only a few of all components available
