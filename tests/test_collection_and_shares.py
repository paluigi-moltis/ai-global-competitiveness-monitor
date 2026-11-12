"""Tests for idempotent collection (merge on keys) and the
usage_shares dataset (Vercel AI Gateway components)."""
from __future__ import annotations

import datetime as dt

import pytest
import pandas as pd

import common
from common import standardise
from common.adoption import usage_shares_components


# ---------------------------------------------------------------------------
# Idempotent merge in write_processed
# ---------------------------------------------------------------------------

def test_write_processed_merge_is_idempotent_and_preserves_history(sandbox):
    df1 = pd.DataFrame([
        {"date": dt.date(2026, 1, 1), "source_model_id": "a", "tokens": 100.0},
        {"date": dt.date(2026, 1, 2), "source_model_id": "a", "tokens": 200.0},
    ])
    keys = common.DATASET_KEYS["usage"]
    common.write_processed("usage", standardise("usage", df1, source="openrouter"),
                           merge_keys=keys)
    path = sandbox / "data" / "processed" / "usage.parquet"

    # re-collect with the same rows plus a new day, and a changed old value
    df2 = pd.DataFrame([
        # same key as day 1 but different value: first-recorded must win
        {"date": dt.date(2026, 1, 1), "source_model_id": "a", "tokens": 999.0},
        {"date": dt.date(2026, 1, 2), "source_model_id": "a", "tokens": 200.0},
        {"date": dt.date(2026, 1, 3), "source_model_id": "a", "tokens": 300.0},
    ])
    common.write_processed("usage", standardise("usage", df2, source="openrouter"),
                           merge_keys=keys)
    got = pd.read_parquet(path)
    assert len(got) == 3                      # no duplicates
    assert got["date"].nunique() == 3         # history preserved
    day1 = got[got["date"] == dt.date(2026, 1, 1)]["tokens"].iloc[0]
    assert day1 == 100.0                      # first-recorded value kept
    # writing identical rows again changes nothing
    common.write_processed("usage", standardise("usage", df2, source="openrouter"),
                           merge_keys=keys)
    assert len(pd.read_parquet(path)) == 3


# ---------------------------------------------------------------------------
# usage_shares schema + Vercel gateway components
# ---------------------------------------------------------------------------

def _shares() -> pd.DataFrame:
    d = dt.date(2026, 11, 10)
    rows = [
        # vercel gateway shares for one day (tokens metric): sum incl Other = 100
        (d, "vercel_gateway", "GLM 5.3", "tokens", 30.0),
        (d, "vercel_gateway", "GPT-6 Luna", "tokens", 20.0),
        (d, "vercel_gateway", "DeepSeek V4.1 Flash", "tokens", 10.0),
        (d, "vercel_gateway", "Other", "tokens", 40.0),
        # spend metric
        (d, "vercel_gateway", "GLM 5.3", "spend", 15.0),
        (d, "vercel_gateway", "GPT-6 Luna", "spend", 45.0),
        (d, "vercel_gateway", "Other", "spend", 40.0),
        # a request-metric row must be ignored (not in metrics)
        (d, "vercel_gateway", "GLM 5.3", "requests", 25.0),
        # another platform's row must be ignored
        (d, "openrouter", "GLM 5.3", "tokens", 50.0),
    ]
    return pd.DataFrame(rows, columns=["date", "source", "source_model_id",
                                       "metric", "share_percent"])


def _model_info() -> pd.DataFrame:
    rows = []
    for smid in ["GLM 5.3", "GPT-6 Luna", "DeepSeek V4.1 Flash", "Other"]:
        m = common.lookup_model("vercel_gateway", smid)
        if m is None:  # e.g. the "Other" aggregate: unmappable by design
            continue
        rows.append({"source": "vercel_gateway", "source_model_id": smid,
                     "model_id": m.model_id, "geography": m.geography,
                     "weights_status": m.weights_status,
                     "company_id": m.company_id})
    return pd.DataFrame(rows)


def test_usage_shares_schema():
    std = standardise("usage_shares", _shares(), source="vercel_gateway")
    assert list(std.columns) == ["date", "source", "source_model_id",
                                 "metric", "share_percent"]
    assert std["share_percent"].dtype == "float64"


def test_vercel_gateway_components_exclude_other(sandbox_with_data):
    comp = usage_shares_components(_shares(), _model_info(), "vercel_gateway",
                                   metrics=("tokens", "spend"))
    toks = comp[comp["component_id"] == "vercel_gateway_tokens_share"]
    # identifiable total = 60% (Other's 40% excluded): China 30+10 (GLM + DeepSeek)
    assert toks[toks["geography"] == "China"]["value"].iloc[0] == 0.40
    assert toks[toks["geography"] == "US"]["value"].iloc[0] == 0.20
    assert toks[toks["geography"] == "EU"].empty  # no EU model in shares
    # shares no longer sum to 1 across geos - that's the identifiable share
    assert toks["value"].sum() == pytest.approx(0.60)

    spend = comp[comp["component_id"] == "vercel_gateway_spend_share"]
    assert spend[spend["geography"] == "China"]["value"].iloc[0] == 0.15
    assert spend[spend["geography"] == "US"]["value"].iloc[0] == 0.45
    # requests metric excluded
    assert "vercel_gateway_requests_share" not in set(comp["component_id"])
