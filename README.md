# AI Global Competitiveness Monitor

A lightweight, transparent data platform for monitoring the development of AI
models and ecosystems across four geographical groups:

- **US**
- **China**
- **EU**
- **RoW** (Rest of World / Undefined)

It compares both AI **capabilities** (benchmark performance) and market
**adoption** (real-world usage), with particular attention to the relative
position of China versus the US and Europe, and tracks the open-weight
ecosystem separately from closed-weight models.

Design principles: simplicity, transparency, reproducibility, maintainability.
No microservices, no orchestration framework, no backend API, no database
server. Two commands and a static dashboard.

## Status

**Phase 1 (foundation) is implemented and tested.** Collectors and the
dashboard land in Phases 2 and 4 - see [Roadmap](#roadmap).

| Component | Status |
|---|---|
| Config schemas (companies, models, mapping, benchmarks, country→geography) | ✅ done |
| Excel weights template (`scripts/build_weights_template.py` → `config/weights.xlsx`) | ✅ done |
| Entity mapping + geography classification | ✅ done, tested |
| Standardised Parquet schemas | ✅ done, tested |
| `process.py` (metrics, indicators, composite indices, historical series) | ✅ done, tested |
| Capability / adoption indicators + composite index math | ✅ done, tested |
| Collector framework + raw archiving | ✅ done |
| OpenRouter collector (current `rankings-daily` Data API) | ✅ implemented |
| Other collectors (Epoch, LMArena, HF, ModelScope, …) | ⏳ Phase 2 |
| Static dashboard (Pico.css + Plotly.js + DuckDB-Wasm) | ⏳ Phase 4 |

## Architecture

```
config/                     hand-maintained reference data (edit these, not code)
  companies.csv             company_id, company_name, hq_country, geography
  models.csv                model_id, model_name, company_id, weights_status
  model_mapping.csv         source, source_model_id -> model_id
  benchmarks.csv            benchmark catalogue (id, category, preferred source)
  country_geography.csv     ISO country code -> US | China | EU | RoW
  weights.xlsx              USER-EDITABLE composite index weights
collectors/                 one module per source; raw responses archived to data/raw/
common/                     mapping, schemas, indicators, index math
data/
  raw/<source>/<date>/      original API responses (reprocessing without refetch)
  processed/                standardised + derived Parquet datasets
web/                        static dashboard (Phase 4)
collect.py                  retrieve + archive + standardise
process.py                  map entities, compute indicators and indices
```

### The two commands

```bash
python collect.py                # all sources (or --source openrouter)
python process.py                # indicators + indices from collected data
```

`process.py` never touches the network: it reads archived/standardised data
and the weights workbook. Editing `config/weights.xlsx` and rerunning
`process.py` recalculates all historical indices instantly - no recollection.

### Technology

Python (pandas + DuckDB-ready), Parquet storage, Excel for weights,
HTML + JavaScript + Pico.css + Plotly.js + DuckDB-Wasm for the dashboard
(static, PWA-compatible; the browser queries Parquet files directly).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python scripts/build_weights_template.py   # (re)generate config/weights.xlsx
pytest                                     # run the test suite
```

**API keys** live in environment variables. Copy `.env.example` to `.env`
(git-ignored) and fill in what you need - `collect.py` and `process.py` load
it automatically via python-dotenv; real environment variables take
precedence. The Vercel AI Gateway source needs no key at all (public export,
CC BY 4.0).

The OpenRouter collector needs an API key (any valid OpenRouter key works;
the Data API is CC BY 4.0 licensed):

```bash
cp .env.example .env          # then set OPENROUTER_API_KEY in .env
python collect.py --source openrouter
python collect.py --source vercel_gateway   # no key needed
python process.py
```

Collection is **idempotent**: observations are keyed by (date, source, id)
and merged into the existing Parquet files - re-running never duplicates
rows or overwrites already-archived history, and snapshots accumulate over
time.

## Entity identification and geography

Simple, manually maintained CSVs instead of entity resolution:

- **companies.csv** assigns each company a `geography` derived from its
  headquarters country via **country_geography.csv** (change classification
  in configuration, not code).
- **models.csv** gives each canonical model a `weights_status` of
  `open`, `closed` or `unknown`. We use the term *open weights*, not open
  source: publicly available weights do not imply an open-source licence.
- **model_mapping.csv** maps each source's model identifiers to canonical
  model IDs. Unresolved ids are logged and written to
  `data/unmatched_review.csv` for manual correction. Models are assigned to
  RoW/Undefined only when their origin genuinely cannot be established.

## Capability indicators

Per benchmark, date and geography:

1. Best model score (percentile-normalised for composites; raw scores kept).
2. Share of models in the global top 10.
3. Share of models in the global top 20.
4. Distinct providers in the global top 10 (raw count + normalised by 10).
5. Distinct providers in the global top 20 (raw count + normalised by 20).

All five are repeated for **open-weight models only**, and open-weight models
are ranked *against other open-weight models* - not filtered from the overall
ranking. This measures the competitive strength and breadth of the
open-weight ecosystem.

Percentile normalisation is relative: it can conceal absolute improvement when
all models improve. The dashboard therefore shows raw scores and historical
score evolution alongside normalised indicators.

Benchmark groups (initial catalogue, in `config/benchmarks.csv`):

- International: MMLU-Pro, GPQA Diamond (knowledge/reasoning); AIME, MATH
  (math); LiveCodeBench, SWE-bench (coding); LiveBench (reasoning);
  LMArena (human preference).
- Chinese: C-Eval, CMMLU, SuperCLUE.

One preferred source/version per benchmark; duplicates are avoided. Each
source's historical coverage and caveats are verified before its collector is
implemented - unavailable metrics are documented, never fabricated.

## Adoption indicators

**OpenRouter** (per geography, excluding the unattributable "other" bucket):

- Share of identifiable tokens.
- Share of estimated spending (⚠ experimental, **zero weight by default**;
  requires an explicit input/output mix assumption and archived prices).
- Open-weight variants of both (share of *total identifiable* traffic).

The identifiable share of total traffic is reported alongside: OpenRouter
publishes only the top 50 models plus one aggregated "other" row, which
cannot be attributed to a geography.

**Vercel AI Gateway** (per geography, same "Other" exclusion):

- Share of identifiable tokens (`vercel_gateway_tokens_share`, weight 1.0).
- Share of identifiable spend (`vercel_gateway_spend_share`, ⚠ experimental,
  **zero weight by default** — spend reflects the gateway's own pricing).

The gateway publishes anonymised daily *percentage shares* (never absolute
volumes), so this source populates a dedicated `usage_shares` dataset and no
absolute numbers are fabricated. Two documented caveats: figures cover only
traffic routed through Vercel's gateway (self-selected sample), and shares
sum to 100% *including* the aggregated "Other" row, so geographical shares
sum to the identifiable share of traffic.

**Downloads** - platforms are kept strictly separate (Hugging Face,
ModelScope, Ollama). Geographical shares are computed *within* each platform;
raw counts are never summed across platforms because counters and definitions
differ. Counter semantics (cumulative vs daily) are verified per platform
before computing changes; if a reliable public metric is unavailable it is
shown as unavailable.

## Composite indices

```
Index(g,t) = Σ w_i · x(i,g,t) / Σ_{i ∈ A(g,t)} w_i
```

- Weights live in **config/weights.xlsx** (component id, description,
  category, weight, notes). Edit only the `weight` column.
- Weights are non-negative and auto-normalised - no need to sum to 100.
- Missing components are **excluded, not zero-filled**; remaining weights are
  renormalised.
- **Coverage** = available weight / total intended weight, reported with
  every index value.
- Historical daily series carry the latest observation at or before each date
  forward (no look-ahead), retaining the observation date for freshness.
- Spending components carry zero default weight until their reliability is
  assessed.

## Data sources

| Source | Purpose | Status |
|---|---|---|
| OpenRouter | usage tokens, estimated spending | implemented (`rankings-daily` Data API, key required, CC BY 4.0) |
| Vercel AI Gateway | model usage shares (tokens/requests/spend) | implemented (public `leaderboard-export`, no key, CC BY 4.0, shares from 2025-10-01) |
| Epoch AI | model + benchmark history | Phase 2 |
| LMArena | human-preference Elo | Phase 2 |
| Artificial Analysis | evaluations/rankings | Phase 2 (API terms to verify) |
| Hugging Face | metadata, downloads (cumulative 30-day counter) | Phase 2 |
| ModelScope | metadata, downloads (CN platform) | Phase 2+ |
| Ollama | catalogue, pull indicators | Phase 2+ |
| LiveBench | benchmark scores | Phase 2 |
| LiveCodeBench | coding scores | Phase 2 |
| SWE-bench | SWE-bench Verified scores | Phase 2 |

Public APIs and documented endpoints only; rate limits and source terms
respected; raw responses archived under `data/raw/` so processing is
repeatable without refetching.

## Testing

```bash
pytest
```

Covers: entity mapping and validation, ranking and top-N shares, provider
counts, open-weight re-ranking, OpenRouter "other"-exclusion, per-platform
download shares, weight normalisation, missing-component renormalisation,
coverage reporting, negative-weight rejection, carry-forward without
look-ahead, and an end-to-end `process.py` run on synthetic data - including
a test that editing `weights.xlsx` changes index values without
recollection.

## Roadmap

1. **Phase 2** - implement remaining collectors, prioritising sources with
   structured historical data (Epoch AI, LMArena, Artificial Analysis,
   Hugging Face), then verify access conditions for the rest.
2. **Phase 3** - extend indicators as real data lands; validate against
   manually calculated examples; exercise missing-data and edge cases.
3. **Phase 4** - dashboard (overview / capabilities / adoption), date
   selection, model/provider drill-downs, static-host + range-request testing.
4. **Phase 5** - idempotent reruns, logging/coverage reports, stale-source
   alerts, contributor documentation.

## Licence

MIT. Source data licences (e.g. OpenRouter CC BY 4.0) are respected and
attributed in the collectors.
