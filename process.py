#!/usr/bin/env python3
"""process.py - apply entity mappings, calculate metrics and indices,
export dashboard-ready Parquet files.

Reads only archived/standardised data (data/raw/ -> collectors' standardised
output or data/processed). Never queries external services, so weight
experiments rerun instantly:

    python process.py

Outputs (data/processed/):
    benchmark_observations.parquet  standardised benchmark scores + geography
    ranked_benchmarks.parquet       per-date rankings with geography/scope
    capability_components.parquet   long-format capability components
    capability_detail.parquet       components + raw scores + contributing models
    adoption_components.parquet     long-format adoption components
    index_daily.parquet             historical daily Capability + Adoption index
    index_components_daily.parquet  carried-forward components used per index date
    models_ref.parquet              canonical model/company reference for the UI
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from dotenv import load_dotenv  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Environment variables may be defined in a repo-root .env (API keys etc.);
# real environment variables take precedence. process.py itself needs no
# network access - this only standardises configuration loading.
load_dotenv(Path(__file__).resolve().parent / ".env")

import common  # noqa: E402  (module import so tests can repoint paths)
from common import GEOGRAPHIES, load_models, load_companies, setup_logging  # noqa: E402
from common.capabilities import capability_components, component_frame  # noqa: E402
from common.adoption import (  # noqa: E402
    openrouter_components, downloads_components,
)
from common.indices import asof_components, composite_index, load_weights  # noqa: E402

log = logging.getLogger("process")

DAILY_INDEX_START = "2025-01-01"
DAILY_INDEX_END = None  # today


def _load_standardised(name: str) -> pd.DataFrame | None:
    path = common.PROCESSED_DIR / f"{name}.parquet"
    if not path.exists():
        log.warning("Missing standardised dataset %s - skipping", path.name)
        return None
    df = pd.read_parquet(path)
    if df.empty:
        log.warning("Empty dataset %s - skipping", path.name)
        return None
    return df


def model_info_frame() -> pd.DataFrame:
    """Flatten mapping: (source, source_model_id) -> model/company/geography."""
    from common import load_model_mapping
    mapping = load_model_mapping()
    models = load_models().set_index("model_id")
    companies = load_companies().set_index("company_id")
    rows = []
    for _, m in mapping.iterrows():
        if m["model_id"] not in models.index:
            log.warning("model_mapping.csv target '%s' not in models.csv - skipped",
                        m["model_id"])
            continue
        mod = models.loc[m["model_id"]]
        comp = companies.loc[mod["company_id"]]
        rows.append({
            "source": m["source"],
            "source_model_id": m["source_model_id"],
            "model_id": m["model_id"],
            "model_name": mod["model_name"],
            "company_id": mod["company_id"],
            "company_name": comp["company_name"],
            "hq_country": comp["hq_country"],
            "geography": comp["geography"],
            "weights_status": mod["weights_status"],
        })
    return pd.DataFrame(rows)


def build_benchmark_observations(model_info: pd.DataFrame) -> pd.DataFrame | None:
    raw = _load_standardised("benchmarks")
    if raw is None:
        return None
    obs = raw.merge(
        model_info[["source", "source_model_id", "model_id", "model_name",
                    "company_id", "company_name", "geography", "weights_status"]],
        on=["source", "source_model_id"], how="inner",
    )
    unmatched = set(zip(raw["source"], raw["source_model_id"])) - set(
        zip(obs["source"], obs["source_model_id"]))
    for src, smid in sorted(unmatched):
        log.warning("Unmapped benchmark observation: %s/%s (add to model_mapping.csv)",
                    src, smid)
    return obs


def build_adoption_components(model_info: pd.DataFrame) -> pd.DataFrame:
    frames = []
    usage = _load_standardised("usage")
    if usage is not None:
        oc = openrouter_components(usage, model_info)
        if not oc.empty:
            frames.append(oc)
    for platform in ("huggingface", "modelscope", "ollama"):
        dl = _load_standardised(f"downloads_{platform}")
        if dl is not None:
            comp = downloads_components(dl, model_info, platform)
            if not comp.empty:
                frames.append(comp)
    # share-based adoption (gateways publishing daily % shares, not absolutes)
    from common.adoption import usage_shares_components
    shares = _load_standardised("usage_shares_vercel_gateway")
    if shares is not None:
        comp = usage_shares_components(shares, model_info, "vercel_gateway",
                                       metrics=("tokens", "spend"))
        if not comp.empty:
            frames.append(comp)
    if not frames:
        return pd.DataFrame(columns=["date", "component_id", "geography", "value"])
    return pd.concat(frames, ignore_index=True)


def build_daily_indices(cap_components: pd.DataFrame,
                        adoption_components: pd.DataFrame,
                        weights: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Historical daily index series for Capability and Adoption.

    - daily calendar grid from DAILY_INDEX_START to today
    - components carried forward (no look-ahead, obs_date retained)
    - one index per (category, date, geography)
    """
    import datetime as dt
    end = dt.date.today() if DAILY_INDEX_END is None else pd.Timestamp(DAILY_INDEX_END)
    dates = pd.date_range(DAILY_INDEX_START, end, freq="D")

    def daily_for(category: str, comps: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        if comps.empty:
            empty = pd.DataFrame(columns=["date", "category", "geography", "index", "coverage"])
            return empty, pd.DataFrame(columns=["date", "category", "component_id",
                                                "geography", "value", "obs_date"])
        asof = asof_components(comps, dates)
        # tag category by component prefix
        prefix = "cap_" if category == "capability" else ""
        idx = composite_index(asof.rename(columns={"date": "date"}), weights)
        idx["category"] = category
        asof["category"] = category
        return idx[["date", "category", "geography", "index", "coverage"]], asof

    cap_idx, cap_asof = daily_for("capability", cap_components)
    # adoption components have no cap_ prefix; same machinery
    ado_idx, ado_asof = daily_for("adoption", adoption_components)

    all_idx = pd.concat([cap_idx, ado_idx], ignore_index=True)
    all_asof = pd.concat([cap_asof, ado_asof], ignore_index=True)
    return all_idx, all_asof


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    weights = load_weights()
    log.info("Loaded %d component weights (%.1f total weight)",
             len(weights), weights["weight"].sum())

    model_info = model_info_frame()
    log.info("Entity map: %d source ids -> %d canonical models",
             len(model_info), model_info["model_id"].nunique())

    # --- capability --------------------------------------------------------
    bench = build_benchmark_observations(model_info)
    if bench is not None:
        # keep the enriched (geography/company-tagged) frame; ensure score dtype
        bench["score"] = pd.to_numeric(bench["score"], errors="coerce")
        common.write_processed("benchmark_observations", bench)
        from common.capabilities import rank_observations
        ranked_all = rank_observations(bench, model_info, open_weights_only=False)
        ranked_open = rank_observations(bench, model_info, open_weights_only=True)
        ranked = pd.concat([
            ranked_all.assign(scope="all"),
            ranked_open.assign(scope="open"),
        ], ignore_index=True)
        common.write_processed("ranked_benchmarks", ranked)
        cap = capability_components(ranked)
        common.write_processed("capability_components", component_frame(cap))
        common.write_processed("capability_detail", cap)
        log.info("Capability components: %d rows", len(cap))
        cap_components = component_frame(cap)
    else:
        log.warning("No benchmark data - capability index will be empty")
        cap_components = pd.DataFrame(columns=["date", "component_id", "geography", "value"])

    # --- adoption ----------------------------------------------------------
    adoption = build_adoption_components(model_info)
    common.write_processed("adoption_components", adoption)
    log.info("Adoption components: %d rows", len(adoption))

    # --- indices -----------------------------------------------------------
    idx, asof = build_daily_indices(cap_components, adoption, weights)
    if not idx.empty:
        idx["index"] = idx["index"].astype(float)
    common.write_processed("index_daily", idx)
    common.write_processed("index_components_daily", asof)
    if not idx.empty:
        last = idx.groupby("category")["date"].max()
        for cat, d in last.items():
            log.info("Index '%s' latest date: %s", cat, pd.Timestamp(d).date())

    # --- reference table for the dashboard ---------------------------------
    models_ref = model_info.drop_duplicates(subset=["model_id"])[[
        "model_id", "model_name", "company_id", "company_name",
        "hq_country", "geography", "weights_status"]]
    common.write_processed("models_ref", models_ref)

    # --- dashboard exports ---------------------------------------------------
    # web/data/ receives copies of everything the browser queries via
    # DuckDB-Wasm, plus meta.json (weights + freshness). Written by process.py
    # so a weight edit refreshes the dashboard without recollection.
    try:
        export_dashboard_data(idx, weights)
    except Exception:  # noqa: BLE001 - dashboard export must not kill processing
        log.exception("Dashboard export failed")

    log.info("Done. Dashboard data in %s", common.PROCESSED_DIR)
    return 0


def export_dashboard_data(idx: pd.DataFrame, weights: pd.DataFrame) -> None:
    """Copy query-ready parquets to web/data/ and write meta.json.

    Files are rewritten as parquet format v1.0 with us-precision timestamps:
    duckdb-wasm 1.29 throws an opaque WebAssembly exception on some
    parquet-2.6 files produced by pyarrow 26 (verified with
    index_components_daily.parquet); v1.0 reads fine and is marginally
    larger.
    """
    import json
    import datetime as dt

    web_data = common.ROOT / "web" / "data"
    web_data.mkdir(parents=True, exist_ok=True)
    for name in ("index_daily", "capability_components", "adoption_components",
                 "capability_detail", "ranked_benchmarks", "models_ref",
                 "index_components_daily"):
        src = common.PROCESSED_DIR / f"{name}.parquet"
        if not src.exists():
            continue
        df = pd.read_parquet(src)
        for col in df.columns:
            if str(df[col].dtype).startswith("datetime"):
                df[col] = df[col].astype("datetime64[us]")
        df.to_parquet(web_data / f"{name}.parquet", engine="pyarrow",
                      coerce_timestamps="us", version="1.0")

    gen_date = dt.date.today().isoformat()
    last_data = ""
    if not idx.empty:
        last_data = pd.Timestamp(idx["date"].max()).date().isoformat()
    # latest observation date behind each carried component (freshness)
    meta = {
        "generated": gen_date,
        "last_data_date": last_data,
        "geographies": GEOGRAPHIES,
        "weights": weights.to_dict(orient="records"),
    }
    (web_data / "meta.json").write_text(json.dumps(meta, indent=2))
    log.info("Dashboard data exported to %s", web_data)


if __name__ == "__main__":
    raise SystemExit(main())
