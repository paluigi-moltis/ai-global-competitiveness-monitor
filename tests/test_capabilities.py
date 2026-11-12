"""Capability indicator tests: ranking, top-N shares, provider counts,
open-weight re-ranking, percentile normalisation."""
from __future__ import annotations

import datetime as dt

import pandas as pd

import common
from common.capabilities import capability_components, rank_observations


def _model_info() -> pd.DataFrame:
    rows = []
    for source, ids in {
        "epoch": ["gpt-5", "deepseek-r1", "mistral-large-2411",
                  "gpt-oss-120b", "glm-4-5"],
    }.items():
        for smid in ids:
            m = common.lookup_model(source, smid)
            rows.append({"source": source, "source_model_id": smid,
                         "model_id": m.model_id, "geography": m.geography,
                         "weights_status": m.weights_status,
                         "company_id": m.company_id})
    return pd.DataFrame(rows)


def _bench() -> pd.DataFrame:
    d1 = dt.date(2026, 1, 1)
    return pd.DataFrame([
        # global ranking: gpt-5 (US, closed) 1st, deepseek-r1 (CN, open) 2nd,
        # mistral-large (EU, closed) 3rd, gpt-oss-120b (US, open) 4th, glm-4-5 (CN, open) 5th
        (d1, "epoch", "mmlu-pro", "gpt-5", 89.0),
        (d1, "epoch", "mmlu-pro", "deepseek-r1", 84.0),
        (d1, "epoch", "mmlu-pro", "mistral-large-2411", 80.0),
        (d1, "epoch", "mmlu-pro", "gpt-oss-120b", 76.0),
        (d1, "epoch", "mmlu-pro", "glm-4-5", 75.0),
    ], columns=["date", "source", "benchmark", "source_model_id", "score"])


def test_ranking_order():
    ranked = rank_observations(_bench(), _model_info())
    top = ranked.nsmallest(2, "rank")
    assert top.iloc[0]["model_id"] == "gpt-5"
    assert top.iloc[1]["model_id"] == "deepseek-r1"


def test_topn_shares_and_provider_counts():
    ranked = rank_observations(_bench(), _model_info())
    cap = capability_components(ranked)
    row = cap[(cap["benchmark"] == "mmlu-pro") & (cap["scope"] == "all")]

    us = row[row["geography"] == "US"].iloc[0]
    assert us["models10"] == 2          # gpt-5 (rank 1), gpt-oss-120b (rank 4)
    assert us["cap_top10"] == 0.2       # 2 of 10 slots
    assert us["cap_providers10"] == 1   # both models are OpenAI -> 1 distinct provider
    assert us["cap_providers10_norm"] == 0.1

    cn = row[row["geography"] == "China"].iloc[0]
    assert cn["models10"] == 2          # deepseek-r1 (rank 2), glm-4-5 (rank 5)
    assert cn["cap_providers10"] == 2   # deepseek + zhipu
    assert cn["cap_top10"] == 0.2

    eu = row[row["geography"] == "EU"].iloc[0]
    assert eu["cap_best"] > 0           # percentile-normalised best score


def test_openweight_reranking():
    """Open models ranked among themselves, not filtered from overall ranking."""
    ranked = rank_observations(_bench(), _model_info(), open_weights_only=True)
    open_ranked = ranked[ranked["weights_status"] == "open"]
    # overall ranks 2,4,5 -> open ranks 1,2,3
    by_open_rank = open_ranked.sort_values("rank")
    assert list(by_open_rank["model_id"]) == ["deepseek-r1", "gpt-oss-120b", "glm-4-5"]
    assert list(by_open_rank["rank"]) == [1.0, 2.0, 3.0]

    cap = capability_components(ranked)
    cn = cap[(cap["scope"] == "open") & (cap["geography"] == "China")].iloc[0]
    assert cn["cap_top10"] == 0.2       # ranks 1+2 among open models -> 2 of 10 slots
    us = cap[(cap["scope"] == "open") & (cap["geography"] == "US")].iloc[0]
    assert us["cap_top10"] == 0.1       # rank 3 among open models


def test_missing_geography_excluded_not_zero():
    ranked = rank_observations(_bench(), _model_info())
    cap = capability_components(ranked)
    # no RoW models in panel -> no RoW rows at all (composite handles absence)
    assert not (cap["geography"] == "RoW").any()


def test_component_ids_follow_weights_template():
    """component ids must match what scripts/build_weights_template.py emits."""
    ranked = rank_observations(_bench(), _model_info())
    from common.capabilities import component_frame
    comp = component_frame(capability_components(ranked))
    assert set(comp["component_id"]).issuperset({
        "cap_mmlu-pro_best", "cap_mmlu-pro_best_open",
        "cap_mmlu-pro_top10", "cap_mmlu-pro_top20_open",
        "cap_mmlu-pro_providers10", "cap_mmlu-pro_providers20",
    })
