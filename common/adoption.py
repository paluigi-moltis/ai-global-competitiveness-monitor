"""Adoption indicators.

OpenRouter shares exclude the unattributable "other" bucket and report the
identifiable share of traffic alongside. Download platforms (Hugging Face,
ModelScope, Ollama) are kept strictly separate: geographical shares are
computed within each platform, never across platforms.
"""
from __future__ import annotations

import pandas as pd

from . import GEOGRAPHIES

# OpenRouter component identifiers (must match config/weights.xlsx component ids)
OPENROUTER_COMPONENTS = [
    "or_tokens_share",
    "or_spend_share",
    "or_tokens_open_share",
    "or_spend_open_share",
]
DOWNLOAD_COMPONENTS = {
    "huggingface": "hf_downloads_share",
    "modelscope": "modelscope_downloads_share",
    "ollama": "ollama_downloads_share",
}


def _share_by_geography(usage: pd.DataFrame, value_col: str,
                        model_info: pd.DataFrame) -> pd.DataFrame:
    """Share of `value_col` per geography, excluding unidentifiable models.

    `usage` columns: date, source, source_model_id, <value_col>, optional weights_status/geography
    Returns rows: date, geography, value, identifiable_total, share, open_value, open_share
    """
    u = usage.merge(
        model_info[["source", "source_model_id", "geography", "weights_status"]],
        on=["source", "source_model_id"], how="left",
    )
    u["geography"] = u["geography"].fillna("RoW")
    # genuinely-unidentifiable traffic: no mapping at all
    unmapped = u["geography"].eq("RoW") & u["weights_status"].isna()
    identifiable = u[~unmapped].copy()

    out_rows = []
    for date, g in identifiable.groupby("date"):
        total = g[value_col].sum()
        if total <= 0:
            continue
        open_mask = g["weights_status"] == "open"
        for geo in GEOGRAPHIES:
            v = g.loc[g["geography"] == geo, value_col].sum()
            vo = g.loc[(g["geography"] == geo) & open_mask, value_col].sum()
            out_rows.append({
                "date": date,
                "geography": geo,
                "value": v,
                "open_value": vo,
                "identifiable_total": total,
                "share": v / total,
                "open_share": (vo / total) if total else 0.0,
            })
        # source-level identifiable share of all traffic (incl. unmapped)
    ident_share = []
    for date, g in u.groupby("date"):
        all_total = g[value_col].sum()
        mapped = g[~(g["weights_status"].isna())][value_col].sum()
        ident_share.append({"date": date, "identifiable_traffic_share":
                            (mapped / all_total) if all_total else None})
    ident = pd.DataFrame(ident_share)

    out = pd.DataFrame(out_rows)
    if out.empty:
        return out
    out = out.merge(ident, on="date", how="left")
    return out


def openrouter_components(usage: pd.DataFrame, model_info: pd.DataFrame) -> pd.DataFrame:
    """OpenRouter adoption components from standardised usage data.

    `usage` must include: date, source, source_model_id, tokens, estimated_spend.
    Produces long-format component rows (date, component_id, geography, value).
    estimated_spend components are emitted only if the column carries values.
    """
    rows: list[pd.DataFrame] = []
    for value_col, comp_base in (("tokens", "or_tokens"), ("estimated_spend", "or_spend")):
        if value_col not in usage.columns or usage[value_col].notna().sum() == 0:
            continue
        sub = usage[["date", "source", "source_model_id", value_col]].rename(
            columns={value_col: "value"})
        shares = _share_by_geography(sub, "value", model_info)
        if shares.empty:
            continue
        base = shares[["date", "geography", "share"]].copy()
        base["component_id"] = f"{comp_base}_share"
        rows.append(base[["date", "component_id", "geography", "share"]].rename(
            columns={"share": "value"}))
        openp = shares[["date", "geography", "open_share"]].copy()
        openp["component_id"] = f"{comp_base}_open_share"
        rows.append(openp[["date", "component_id", "geography", "open_share"]].rename(
            columns={"open_share": "value"}))
    if not rows:
        return pd.DataFrame(columns=["date", "component_id", "geography", "value"])
    return pd.concat(rows, ignore_index=True)


def downloads_components(downloads: pd.DataFrame, model_info: pd.DataFrame,
                         platform: str) -> pd.DataFrame:
    """Geographical download shares within one platform.

    IMPORTANT: platform download counters have different semantics. This
    consumes standardised `downloads` rows produced by the platform collector,
    which is responsible for defining what a "download" observation means
    (cumulative level or daily delta - documented in the collector).
    """
    comp_id = DOWNLOAD_COMPONENTS[platform]
    sub = downloads[downloads["source"] == platform][
        ["date", "source", "source_model_id", "downloads"]].rename(
        columns={"downloads": "value"})
    if sub.empty:
        return pd.DataFrame(columns=["date", "component_id", "geography", "value"])
    shares = _share_by_geography(sub, "value", model_info)
    if shares.empty:
        return pd.DataFrame(columns=["date", "component_id", "geography", "value"])
    out = shares[["date", "geography", "share"]].copy()
    out["component_id"] = comp_id
    return out[["date", "component_id", "geography", "share"]].rename(
        columns={"share": "value"})
