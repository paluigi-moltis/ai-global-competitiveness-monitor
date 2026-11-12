"""Generate config/weights.xlsx from config/benchmarks.csv + adoption components.

Run from the repo root:  python scripts/build_weights_template.py

The workbook is the user-facing control file for composite index weights.
Structure:
  - Sheet "Weights": component_id, description, category, weight, notes
  - Sheet "README": how to edit weights
Weights need not sum to anything in particular; process.py normalises them.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BENCHMARKS_CSV = ROOT / "config" / "benchmarks.csv"

# Default capability weights per indicator type (best score counts double).
CAPABILITY_WEIGHTS = {
    "best": 2.0,
    "top10": 1.0,
    "top20": 1.0,
    "providers10": 1.0,
    "providers20": 1.0,
}

INDICATOR_LABELS = {
    "best": "Best model score (percentile-normalised)",
    "top10": "Share of global top 10 models",
    "top20": "Share of global top 20 models",
    "providers10": "Distinct providers in global top 10 (normalised by 10)",
    "providers20": "Distinct providers in global top 20 (normalised by 20)",
}

ADOPTION_COMPONENTS = [
    ("or_tokens_share", "OpenRouter: share of identifiable tokens", "adoption.openrouter_usage", 1.0,
     "Excludes the unattributable 'other' bucket."),
    ("or_spend_share", "OpenRouter: share of estimated spending", "adoption.openrouter_spend", 0.0,
     "EXPERIMENTAL. Estimated from tokens with an assumed input/output mix; "
     "zero weight by default until reliability is assessed."),
    ("or_tokens_open_share", "OpenRouter: share of identifiable tokens from open-weight models",
     "adoption.openrouter_open_usage", 1.0, ""),
    ("or_spend_open_share", "OpenRouter: share of estimated spending from open-weight models",
     "adoption.openrouter_open_spend", 0.0, "EXPERIMENTAL; see or_spend_share."),
    ("hf_downloads_share", "Hugging Face: share of downloads (open-weight ecosystem)",
     "adoption.huggingface_downloads", 1.0,
     "Platform-specific: never summed with other platforms."),
    ("modelscope_downloads_share", "ModelScope: share of downloads (open-weight ecosystem)",
     "adoption.modelscope_downloads", 1.0,
     "Platform-specific: never summed with other platforms."),
    ("ollama_downloads_share", "Ollama: share of pulls (open-weight ecosystem)",
     "adoption.ollama_downloads", 1.0,
     "Only populated if reliable public pull data is available."),
]

CATEGORY_LABELS = {
    "general_knowledge_reasoning": "International benchmarks",
    "mathematics": "International benchmarks",
    "coding": "International benchmarks",
    "general_reasoning": "International benchmarks",
    "human_preference": "International benchmarks",
    "chinese_benchmarks": "Chinese benchmarks",
}


def build_rows(benchmarks_csv) -> list[dict]:
    rows: list[dict] = []
    benches = pd.read_csv(benchmarks_csv)
    for _, b in benches.iterrows():
        bid = b["benchmark_id"]
        cat = CATEGORY_LABELS.get(b["category"], b["category"])
        for kind, w in CAPABILITY_WEIGHTS.items():
            comp = f"cap_{bid}_{kind}"
            desc = f"{b['benchmark_name']}: {INDICATOR_LABELS[kind]}"
            notes = ""
            if b["category"] == "chinese_benchmarks":
                notes = "Chinese-language benchmark; captures China-market strength."
            if kind in ("providers10", "providers20"):
                notes = (notes + " " if notes else "") + "Normalised by ranking size in composites; raw counts shown in dashboard."
            rows.append({
                "component_id": comp,
                "description": desc,
                "category": cat,
                "weight": w,
                "notes": notes,
            })
            # Open-weight variant (ranked among open-weight models only).
            rows.append({
                "component_id": f"{comp}_open",
                "description": f"{b['benchmark_name']}: {INDICATOR_LABELS[kind]} (open-weight only)",
                "category": cat,
                "weight": w,
                "notes": "Open-weight models ranked against open-weight models, not filtered from overall ranking."
                         + (" " + notes if notes else ""),
            })
    for comp, desc, cat, w, notes in ADOPTION_COMPONENTS:
        rows.append({
            "component_id": comp,
            "description": desc,
            "category": cat,
            "weight": w,
            "notes": notes,
        })
    return rows


def main() -> None:
    benchmarks_csv = ROOT / "config" / "benchmarks.csv"
    output = ROOT / "config" / "weights.xlsx"
    rows = build_rows(benchmarks_csv)
    weights = pd.DataFrame(rows)

    readme = pd.DataFrame({
        "instructions": [
            "weights.xlsx - composite index weights",
            "",
            "1. Edit ONLY the 'weight' column on the Weights sheet.",
            "2. Weights must be non-negative (0 disables a component).",
            "3. Do not normalise to 100: process.py normalises automatically.",
            "4. Missing components are excluded from the index (not treated as zero)",
            "   and remaining weights are renormalised; coverage is reported.",
            "5. component_id values must not be renamed - process.py matches on them.",
            "6. After saving, rerun:  python process.py",
            "",
            "Index formula for geography g at date t:",
            "  Index(g,t) = sum_i w_i * x(i,g,t) / sum_i in A(g,t) w_i",
            "  where A(g,t) = components available for that geography and date.",
            "",
            "Sheets:",
            "  Weights  - component ids, descriptions, categories, weights, notes.",
            "  README   - this sheet.",
        ]
    })

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        weights.to_excel(writer, sheet_name="Weights", index=False)
        readme.to_excel(writer, sheet_name="README", index=False)

        for sheet in ("Weights", "README"):
            ws = writer.book[sheet]
            for col_idx, width in ((1, 34), (2, 62), (3, 28), (4, 10), (5, 60)):
                ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = width
            if sheet == "README":
                ws.column_dimensions["A"].width = 100

    print(f"Wrote {output} with {len(weights)} components.")


if __name__ == "__main__":
    main()
