"""Shared helpers: config loading, entity mapping, IO, and standard schemas."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

log = logging.getLogger("ai-monitor")

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
WEB_DATA_DIR = ROOT / "web" / "data"

GEOGRAPHIES = ["US", "China", "EU", "RoW"]


# ---------------------------------------------------------------------------
# Configuration loading
# ---------------------------------------------------------------------------

def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    return df


@lru_cache(maxsize=1)
def load_companies() -> pd.DataFrame:
    df = _read_csv(CONFIG_DIR / "companies.csv")
    required = {"company_id", "company_name", "hq_country", "geography"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"companies.csv missing columns: {sorted(missing)}")
    if df["company_id"].duplicated().any():
        dupes = df.loc[df["company_id"].duplicated(), "company_id"].tolist()
        raise ValueError(f"Duplicate company_id values: {dupes}")
    return df


@lru_cache(maxsize=1)
def load_country_geography() -> dict[str, str]:
    df = _read_csv(CONFIG_DIR / "country_geography.csv")
    return dict(zip(df.iloc[:, 0], df.iloc[:, 1]))


@lru_cache(maxsize=1)
def load_models() -> pd.DataFrame:
    df = _read_csv(CONFIG_DIR / "models.csv")
    required = {"model_id", "model_name", "company_id", "weights_status"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"models.csv missing columns: {sorted(missing)}")
    dupes = df.loc[df["model_id"].duplicated(), "model_id"].tolist()
    if dupes:
        raise ValueError(f"Duplicate model_id values: {dupes}")
    bad_status = ~df["weights_status"].isin(["open", "closed", "unknown"])
    if bad_status.any():
        raise ValueError(
            f"models.csv: weights_status must be open/closed/unknown, got: "
            f"{df.loc[bad_status, ['model_id', 'weights_status']].to_dict('records')}"
        )
    companies = load_companies()
    unknown = set(df["company_id"]) - set(companies["company_id"])
    if unknown:
        raise ValueError(f"models.csv references unknown company_id values: {sorted(unknown)}")
    return df


@lru_cache(maxsize=1)
def load_model_mapping() -> pd.DataFrame:
    df = _read_csv(CONFIG_DIR / "model_mapping.csv")
    required = {"source", "source_model_id", "model_id"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"model_mapping.csv missing columns: {sorted(missing)}")
    return df


@lru_cache(maxsize=1)
def load_benchmarks() -> pd.DataFrame:
    df = _read_csv(CONFIG_DIR / "benchmarks.csv")
    required = {"benchmark_id", "benchmark_name", "category", "preferred_source"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"benchmarks.csv missing columns: {sorted(missing)}")
    return df


def clear_config_cache() -> None:
    """Drop cached config DataFrames (used by tests that rewrite config files)."""
    for fn in (load_companies, load_country_geography, load_models,
               load_model_mapping, load_benchmarks):
        fn.cache_clear()


# ---------------------------------------------------------------------------
# Entity mapping
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelInfo:
    model_id: str
    model_name: str
    company_id: str
    company_name: str
    hq_country: str
    geography: str
    weights_status: str


def lookup_model(source: str, source_model_id: str,
                 exclude: set[str] | None = None) -> ModelInfo | None:
    """Resolve a (source, source_model_id) pair to canonical model info.

    `exclude` is a set of model_ids to skip (used when resolving an
    unmapped source id to the *next* best candidate).
    """
    models = load_models().set_index("model_id")
    companies = load_companies().set_index("company_id")
    mapping = load_model_mapping()
    hits = mapping[
        (mapping["source"] == source) & (mapping["source_model_id"] == source_model_id)
    ]
    if exclude:
        hits = hits[~hits["model_id"].isin(exclude)]
    if hits.empty:
        return None
    if len(hits) > 1:
        log.warning("Ambiguous mapping for %s/%s: %s",
                    source, source_model_id, hits["model_id"].tolist())
    model_id = hits.iloc[0]["model_id"]
    if model_id not in models.index:
        log.warning("Mapping target model_id '%s' not in models.csv", model_id)
        return None
    m = models.loc[model_id]
    c = companies.loc[m["company_id"]]
    return ModelInfo(
        model_id=model_id,
        model_name=m["model_name"],
        company_id=m["company_id"],
        company_name=c["company_name"],
        hq_country=c["hq_country"],
        geography=c["geography"],
        weights_status=m["weights_status"],
    )


def model_row(model_id: str) -> ModelInfo | None:
    """Canonical model info by model_id, or None if unknown."""
    models = load_models()
    row = models[models["model_id"] == model_id]
    if row.empty:
        return None
    m = row.iloc[0]
    c = load_companies().set_index("company_id").loc[m["company_id"]]
    return ModelInfo(
        model_id=m["model_id"],
        model_name=m["model_name"],
        company_id=m["company_id"],
        company_name=c["company_name"],
        hq_country=c["hq_country"],
        geography=c["geography"],
        weights_status=m["weights_status"],
    )


def resolve_with_unmatched(source: str, source_model_ids: list[str]) -> tuple[dict[str, ModelInfo], list[str]]:
    """Resolve many ids at once; returns (resolved, unmatched_ids)."""
    resolved: dict[str, ModelInfo] = {}
    unmatched: list[str] = []
    for smid in source_model_ids:
        info = lookup_model(source, smid)
        if info is None:
            unmatched.append(smid)
        else:
            resolved[smid] = info
    return resolved, unmatched


def write_unmatched_review(source: str, unmatched: list[str], path: Path | None = None) -> None:
    """Write unresolved source model ids to data/unmatched_review.csv for manual mapping."""
    if not unmatched:
        return
    path = path or (DATA_DIR / "unmatched_review.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    new_rows = pd.DataFrame({
        "source": [source] * len(unmatched),
        "source_model_id": sorted(set(unmatched)),
        "model_id": "",
    })
    if path.exists():
        existing = pd.read_csv(path, dtype=str).fillna("")
        combined = pd.concat([existing, new_rows]).drop_duplicates(
            subset=["source", "source_model_id"], keep="last"
        )
        combined.to_csv(path, index=False)
    else:
        new_rows.to_csv(path, index=False)
    log.warning("Unmatched ids for %s appended to %s", source, path)


# ---------------------------------------------------------------------------
# Standardised dataset schemas (canonical column order and dtypes)
# ---------------------------------------------------------------------------

STANDARD_SCHEMAS: dict[str, dict] = {
    "usage": {
        "columns": ["date", "source", "source_model_id", "tokens", "estimated_spend"],
        "dtypes": {"tokens": "float64", "estimated_spend": "float64"},
    },
    "benchmarks": {
        "columns": ["date", "benchmark", "source", "source_model_id", "score", "rank"],
        "dtypes": {"score": "float64", "rank": "float64"},
    },
    "downloads": {
        "columns": ["date", "source", "source_model_id", "downloads"],
        "dtypes": {"downloads": "float64"},
    },
    "model_metadata": {
        "columns": ["date", "source", "source_model_id", "company_name",
                    "weights_status", "release_date"],
        "dtypes": {},
    },
}


def standardise(dataset: str, df: pd.DataFrame, *, source: str | None = None) -> pd.DataFrame:
    """Coerce a collector frame to the canonical schema for `dataset`.

    Adds any missing canonical columns as NA, reorders columns, applies
    canonical dtypes, and (optionally) stamps the source column.
    Extra source-specific columns are dropped (keep them in raw data).
    """
    spec = STANDARD_SCHEMAS[dataset]
    out = df.copy()
    if source is not None:
        out["source"] = source
    for col in spec["columns"]:
        if col not in out.columns:
            out[col] = pd.NA
    out = out[spec["columns"]]
    for col, dtype in spec["dtypes"].items():
        out[col] = pd.to_numeric(out[col], errors="coerce").astype(dtype)
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"]).dt.date
    if "release_date" in out.columns:
        out["release_date"] = pd.to_datetime(
            out["release_date"], errors="coerce"
        ).dt.date
    return out


def write_processed(name: str, df: pd.DataFrame) -> Path:
    """Write a processed dataset as Parquet; returns the file path."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / f"{name}.parquet"
    df.to_parquet(path, index=False)
    log.info("Wrote %s (%d rows)", path, len(df))
    return path


def read_processed(name: str) -> pd.DataFrame:
    path = PROCESSED_DIR / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run collect.py/process.py first")
    return pd.read_parquet(path)


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
