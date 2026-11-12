"""Capability indicators.

For every benchmark x date x geography:
  - best score (percentile-normalised)
  - share of models in the global top 10 / top 20
  - distinct providers in the global top 10 / top 20 (raw + normalised by ranking size)

All indicators have an open-weight variant. Open-weight models are ranked
against other open-weight models only (not filtered from the overall
ranking) - this measures the strength and breadth of the open ecosystem.

No look-ahead: each date uses only observations dated on or before it.
"""
from __future__ import annotations

import pandas as pd

from . import GEOGRAPHIES

INDICATOR_KINDS = ["best", "top10", "top20", "providers10", "providers20"]


def rank_observations(bench: pd.DataFrame, model_info: pd.DataFrame,
                      open_weights_only: bool = False) -> pd.DataFrame:
    """For each (date, benchmark), rank model scores and attach geography/company.

    `bench` columns: date, benchmark, source, source_model_id, score
    `model_info` columns: source, source_model_id, model_id, geography, weights_status, company_id
    Returns one row per (date, benchmark, source_model_id) with rank and geo.
    """
    # drop enrichment columns if the frame was already merged with model info
    # (idempotent: process.py passes enriched observations here)
    enrichment = ["model_id", "model_name", "company_id", "company_name",
                  "geography", "weights_status"]
    bench = bench.drop(columns=[c for c in enrichment if c in bench.columns])
    b = bench.merge(
        model_info[["source", "source_model_id", "model_id", "geography",
                    "weights_status", "company_id"]],
        on=["source", "source_model_id"], how="inner",
    )
    if b.empty:
        return b.assign(rank=pd.Series(dtype="float64"))
    if open_weights_only:
        b = b[b["weights_status"] == "open"]
    b = b.sort_values(["date", "benchmark", "score"], ascending=[True, True, False])
    b["rank"] = b.groupby(["date", "benchmark"])["score"].rank(
        method="min", ascending=False
    ).astype("float64")
    return b


def percentile_normalise_best(ranked: pd.DataFrame) -> pd.Series:
    """Normalise best scores to their percentile position among models evaluated
    on the same benchmark and date (0-1, higher = better).

    Percentile of the top score within the score distribution of that
    (date, benchmark) panel: rank of best score / number of models evaluated.
    """
    ranked = ranked.sort_values(["date", "benchmark", "score"], ascending=[True, True, False])
    # percentile position of a score: (number of models scoring strictly below) / (n - 1)
    def _pct(g: pd.DataFrame) -> pd.Series:
        n = len(g)
        if n <= 1:
            return pd.Series(1.0, index=g.index)
        scores = g["score"].rank(ascending=False, method="max")  # rank 1 = best
        return (n - scores) / (n - 1)
    return ranked.groupby(["date", "benchmark"], group_keys=False).apply(_pct).rename("best_pct")


def capability_components(ranked: pd.DataFrame) -> pd.DataFrame:
    """Aggregate ranked observations into per-(date, benchmark, geography) components.

    Output columns:
      date, benchmark, geography, scope(all|open),
      cap_best (percentile-normalised best score),
      cap_top10, cap_top20 (share of global top-N slots held),
      cap_providers10, cap_providers20 (distinct providers; raw counts),
      cap_providers10_norm, cap_providers20_norm (counts / ranking size),
      models10, models20 (contributing model counts)
    """
    ranked = ranked.copy()
    ranked["scope"] = "all"

    parts = [ranked]
    open_only = ranked[ranked["weights_status"] == "open"].copy()
    if not open_only.empty:
        # re-rank open-weight models among themselves
        open_only = open_only.sort_values(["date", "benchmark", "score"],
                                          ascending=[True, True, False])
        open_only["rank"] = open_only.groupby(["date", "benchmark"])["score"].rank(
            method="min", ascending=False
        ).astype("float64")
        open_only["scope"] = "open"
        parts.append(open_only)
    panel = pd.concat(parts, ignore_index=True)

    rows = []
    for (date, bench_id, scope), g in panel.groupby(["date", "benchmark", "scope"]):
        n = len(g)
        for geo in GEOGRAPHIES:
            geo_rows = g[g["geography"] == geo]
            if geo_rows.empty:
                continue
            # best model for this geography = highest score
            best_row = geo_rows.sort_values("score", ascending=False).iloc[0]
            in10 = geo_rows[geo_rows["rank"] <= 10]
            in20 = geo_rows[geo_rows["rank"] <= 20]
            prov10 = in10["company_id"].nunique()
            prov20 = in20["company_id"].nunique()
            rows.append({
                "date": date,
                "benchmark": bench_id,
                "geography": geo,
                "scope": scope,
                "cap_best": best_row["score"],  # raw; normalised later
                "best_model_id": best_row["model_id"],
                "best_company_id": best_row["company_id"],
                "cap_top10": len(in10) / 10,
                "cap_top20": len(in20) / 20,
                "cap_providers10": prov10,
                "cap_providers20": prov20,
                "cap_providers10_norm": prov10 / 10,
                "cap_providers20_norm": prov20 / 20,
                "models10": len(in10),
                "models20": len(in20),
                "panel_size": n,
            })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # percentile-normalise best scores within (date, benchmark, scope) panels
    out = out.sort_values(["date", "benchmark", "scope", "cap_best"],
                          ascending=[True, True, True, False])
    out["cap_best"] = out.groupby(["date", "benchmark", "scope"])["cap_best"].transform(
        lambda s: s.rank(pct=True, method="min")
    )
    return out


def component_frame(cap: pd.DataFrame) -> pd.DataFrame:
    """Melt the capability components into (date, component_id, geography, value, scope)."""
    fields = [
        ("cap_best", "best"), ("cap_top10", "top10"), ("cap_top20", "top20"),
        ("cap_providers10_norm", "providers10"), ("cap_providers20_norm", "providers20"),
    ]
    frames = []
    for col, kind in fields:
        sel = cap[["date", "benchmark", "geography", "scope", col]].rename(columns={col: "value"})
        sel["kind"] = kind
        sel["scope_suffix"] = ""
        frames.append(sel)
        sel_open = sel.copy()
        sel_open["scope_suffix"] = "_open"
        frames.append(sel_open)
    out = pd.concat(frames, ignore_index=True)
    # keep only: all-scope rows with plain suffix, open-scope rows with _open suffix
    keep = out[
        ~((out["scope_suffix"] == "_open") & (out["scope"] != "open"))
        & ~((out["scope_suffix"] == "") & (out["scope"] != "all"))
    ]
    keep["component_id"] = (
        "cap_" + keep["benchmark"] + "_" + keep["kind"] + keep["scope_suffix"]
    )
    return keep[["date", "component_id", "geography", "value", "scope", "kind"]]
