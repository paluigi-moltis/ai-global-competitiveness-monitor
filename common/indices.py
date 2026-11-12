"""Composite index calculation.

Index(g,t) = sum_i w_i * x(i,g,t) / sum_{i in A(g,t)} w_i

- Weights are read from config/weights.xlsx (Weights sheet).
- Weights are non-negative; they are normalised automatically.
- Components missing for (g,t) are excluded (never treated as zero);
  remaining weights are renormalised.
- Coverage = available weight / total intended weight (over components
  with weight > 0 that the pipeline can in principle produce).
- Historical series are built by carrying the latest observation at or
  before each index date forward (no look-ahead); the observation date
  is retained for freshness display.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import GEOGRAPHIES


def _config_dir():
    from . import CONFIG_DIR
    return Path(CONFIG_DIR)


class WeightConfigError(ValueError):
    pass


def load_weights(path: Path | None = None) -> pd.DataFrame:
    """Read the Weights sheet; validate ids and non-negativity. Returns
    DataFrame indexed by component_id with columns weight, description, category."""
    path = path or (_config_dir() / "weights.xlsx")
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found - run scripts/build_weights_template.py first")
    df = pd.read_excel(path, sheet_name="Weights")
    required = {"component_id", "weight"}
    missing = required - set(df.columns)
    if missing:
        raise WeightConfigError(f"weights.xlsx missing columns: {sorted(missing)}")
    df["component_id"] = df["component_id"].astype(str).str.strip()
    if df["component_id"].duplicated().any():
        dupes = df.loc[df["component_id"].duplicated(), "component_id"].tolist()
        raise WeightConfigError(f"Duplicate component_id values: {dupes}")
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    if df["weight"].isna().any():
        bad = df.loc[df["weight"].isna(), "component_id"].tolist()
        raise WeightConfigError(f"Non-numeric weights for: {bad}")
    if (df["weight"] < 0).any():
        bad = df.loc[df["weight"] < 0, "component_id"].tolist()
        raise WeightConfigError(f"Negative weights are not allowed: {bad}")
    return df.set_index("component_id")[["weight", "description", "category"]]


def composite_index(components: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    """Compute index values from long-format components.

    `components`: date, component_id, geography, value
    `weights`: DataFrame indexed by component_id with a `weight` column.
    Returns: date, geography, index, coverage.
    """
    if components.empty:
        return pd.DataFrame(columns=["date", "geography", "index", "coverage"])
    c = components.copy()
    c = c[c["component_id"].isin(weights.index)]
    if (weights["weight"] < 0).any():
        bad = weights.index[weights["weight"] < 0].tolist()
        raise WeightConfigError(f"Negative weights are not allowed: {bad}")
    c["weight"] = weights.loc[c["component_id"], "weight"].values
    c = c[c["weight"] > 0]
    if c.empty:
        return pd.DataFrame(columns=["date", "geography", "index", "coverage"])

    total_weight = weights.loc[weights["weight"] > 0, "weight"].sum()

    out = []
    for (date, geo), g in c.groupby(["date", "geography"]):
        w_avail = g["weight"].sum()
        idx = (g["value"] * g["weight"]).sum() / w_avail if w_avail > 0 else np.nan
        out.append({
            "date": date,
            "geography": geo,
            "index": idx,
            "coverage": w_avail / total_weight if total_weight else np.nan,
        })
    res = pd.DataFrame(out)
    res["geography"] = pd.Categorical(res["geography"], categories=GEOGRAPHIES,
                                      ordered=True)
    return res.sort_values(["date", "geography"]).reset_index(drop=True)


def asof_components(components: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Carry components forward in time with no look-ahead.

    For each index date, each (component_id, geography) takes the latest
    observation dated on or before it. Observation freshness is kept in
    `obs_date`.
    """
    if components.empty:
        return pd.DataFrame(columns=["date", "component_id", "geography",
                                     "value", "obs_date"])
    c = components.copy()
    c["date"] = pd.to_datetime(c["date"])
    c = c.sort_values("date")
    frames = []
    for (comp, geo), g in c.groupby(["component_id", "geography"]):
        g = g.drop_duplicates("date", keep="last").set_index("date")
        idx = dates[dates >= g.index.min()]
        if idx.empty:
            continue
        g = g.assign(obs_date=g.index)  # carried through ffill below
        carried = g.reindex(g.index.union(idx)).ffill().reindex(idx)
        carried["date"] = idx
        carried["component_id"] = comp
        carried["geography"] = geo
        frames.append(carried.reset_index(drop=True))
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if out.empty:
        return pd.DataFrame(columns=["date", "component_id", "geography",
                                     "value", "obs_date"])
    return out[["date", "component_id", "geography", "value", "obs_date"]]
