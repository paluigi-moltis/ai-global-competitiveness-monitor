# Methodology & Sources

This document records data-source definitions, limitations and methodological
decisions. It is the reference for "why is this metric defined this way".

## Geographical classification

- Companies are classified by **headquarters country** (`config/companies.csv`),
  mapped to US / China / EU / RoW via `config/country_geography.csv`.
- Country→geography assignments are configuration, not code: reclassifications
  (e.g. UK→EU policy changes) never require code changes.
- A model inherits the geography of its releasing company. Models whose origin
  genuinely cannot be established are RoW/Undefined - never guessed.

## Weights status

`open` means publicly downloadable weights. It does **not** imply an
open-source licence (usage terms vary: Llama community licence, Qwen licence,
Apache 2.0, research-only, etc.). `unknown` is used when weights availability
is genuinely unclear.

## Benchmarks

See `config/benchmarks.csv` for the catalogue with preferred sources.

### Known limitations

- **Multiple versions**: MATH, AIME and other benchmarks have editions and
  subset conventions (e.g. MATH-500). Mixing versions inflates apparent
  progress. Each benchmark row documents the chosen version; collectors must
  not mix.
- **Double counting**: several providers report scores for the same benchmark
  (e.g. Epoch and LiveBench both carry LiveBench results). One preferred
  source per benchmark; other sources' rows for the same benchmark are
  ignored by process.py.
- **Chinese benchmarks** (C-Eval, CMMLU, SuperCLUE): availability of
  systematic *historical* score series is limited, especially for non-Chinese
  models. Components are defined in the weights template but may show as
  unavailable until a reliable source is wired in - they carry weight in the
  template, so coverage will dip until then; this is intentional and visible
  rather than hidden.
- **Contamination**: static benchmarks saturate. Prefer contamination-managed
  benchmarks (LiveBench refreshes monthly; LiveCodeBench uses post-cutoff
  problems) for trend claims.

### Normalisation decision

Benchmark scores live on different scales (accuracy %, Elo, pass@1). For
composite calculations the best score per benchmark is converted to its
**percentile position among models evaluated on the same benchmark and date**.
Raw scores and ranks are retained in `ranked_benchmarks` and
`capability_detail`, and the dashboard shows raw score evolution because
percentiles conceal absolute progress.

## Capability indicators

For each (benchmark, date, geography), with `N ∈ {10, 20}`:

- `best`: percentile-normalised best score of the geography's best model.
- `topN share`: (# of the geography's models in the global top N) / N.
- `providersN`: distinct releasing companies of the geography's models in the
  global top N; used in composites as count/N, shown raw in the dashboard.
- `_open` variants: same five indicators computed on an open-weights-only
  ranking. **Open models are re-ranked among themselves**, not filtered from
  the overall ranking: a Chinese open model ranked #2 overall and #1 among
  open models counts as the open-ranking leader. This measures the strength
  and breadth of the open-weight ecosystem specifically.

## Adoption indicators

### OpenRouter usage

- Source: `rankings-daily` Data API (CC BY 4.0). Top 50 public models per day
  by total tokens + one aggregated `other` row. History from 2025-01-01.
- **"other" exclusion**: the long-tail row cannot be attributed to a
  geography. All geographical shares use identifiable traffic only; the
  identifiable share of total traffic is computed and displayed so users see
  how much of the market the shares cover.
- **Token comparability**: tokens are counted with each provider's own
  tokenizer (documented by OpenRouter). Cross-geography token comparisons are
  therefore approximate; this is a shared caveat of all OpenRouter-derived
  analyses.
- **Variants**: OpenRouter ranks model *variants* separately
  (`vendor/model:free` etc.). Mapping accounts for the main variants;
  unmapped variants land in `data/unmatched_review.csv`.

### Vercel AI Gateway usage shares

- Source: public `leaderboard-export` API (`vercel.com/api/ai/leaderboard-export`),
  CC BY 4.0, no authentication, cached 24h upstream. Daily share history
  from 2025-10-01.
- **Shares, not absolutes**: only percentage shares of tokens/requests/spend
  are published. Stored in the `usage_shares` dataset; absolute volumes are
  never derived or fabricated.
- **Attribution**: mapped via display names in `model_mapping.csv`
  (`source=vercel_gateway`); the `labs` dataset (clean creator slugs) can
  cross-check mappings. The aggregated "Other" row stays unmapped and is
  excluded from geographical shares - geographical shares therefore sum to
  the identifiable share of gateway traffic, not to 100%.
- **Self-selection caveat**: reflects traffic routed through Vercel AI
  Gateway only. Treat as one market sample alongside OpenRouter, not a
  total-market measure; both are share-based and never summed.
- Attribution line when republishing: © 2026 Vercel. "AI Gateway Leaderboard
  Data" is licensed under CC BY 4.0.

### Estimated spending (EXPERIMENTAL, zero default weight)

Estimated spend cannot be reconstructed accurately from total tokens. If
implemented it must use:

```
estimated_spend = tokens × (input_share × input_price + output_share × output_price)
```

with an explicitly documented input/output mix assumption and **archived
historical prices** where available (otherwise labelled "current prices").
Zero weight by default until reliability is assessed.

### Epoch AI (benchmarks)

- Source: public `benchmark_data.zip` (epoch.ai/data), CC BY 4.0, no auth.
- Ingests GPQA Diamond, MATH Level 5, OTIS Mock AIME 2024-2025 (proxy for
  AIME-class competition math), SWE-bench Verified (Epoch's own runs).
- `date` is the model release date (Epoch does not expose per-row evaluation
  dates); scores normalised to 0-1 via the zip's `benchmark_metadata.csv`
  scale column.
- Epoch model-version ids carry reasoning-effort suffixes (`_high`, `_max`,
  `_64K`, …); all variants of a model map to the same canonical model.

### LiveBench

- Source: per-release CSVs (`table_<release>.csv`) published in the
  LiveBench/livebench.github.io repo - 11 releases, 2024-06-24 → 2026-06-25.
- Score = mean over all task columns / 100 (site's own averaging).
- Caveat: LiveBench 2.0 (2026-06-25) changed the task mix; cross-release
  comparability is approximate around that date. Each release is stored as a
  separate dated observation, never replacing earlier ones.

### Download counters (Hugging Face / ModelScope / Ollama)

All three publish **cumulative levels** with undocumented or rolling-window
semantics. The pipeline stores levels only; no daily increments are derived
anywhere. Geographical shares are computed within each platform per
snapshot; raw counts are never summed across platforms.

## Historical calculation rules

- Daily index series are built on a calendar grid from 2025-01-01.
- Components are **carried forward** from their latest observation at or
  before the index date (`asof` join). A benchmark scored 2026-03-10 is used
  for index dates 2026-03-10..until superseded.
- **No look-ahead**: an observation dated after an index date never influences
  it.
- **Freshness retained**: `obs_date` accompanies every carried component;
  the dashboard exposes it so users can see how stale a component is.
- Coverage is reported per (date, geography): available weight / total
  intended weight.

## API keys and configuration

All keys are read from environment variables; `collect.py`/`process.py`
load a repo-root `.env` via python-dotenv (`.env.example` documents every
supported variable, `.env` is git-ignored). Never hardcode keys; the
frontend never receives any key.

| Variable | Source | Required |
|---|---|---|
| `OPENROUTER_API_KEY` | OpenRouter rankings-daily | yes for `--source openrouter` |
| `VERCEL_AI_GATEWAY_API_KEY` | Vercel AI Gateway | no (public endpoint) |

## Known data gaps (documented, not fabricated)

- No reliable historical daily usage data before OpenRouter's dataset start
  (2025-01-01).
- Spending estimates absent until prices are archived.
- **LMArena**: leaderboard API returns 403 to unauthenticated clients; the
  human-preference component is empty until an accessible historical source
  is found (HF battle datasets are preference pairs, not Elo series).
- **LiveCodeBench**: reachable as an HF dataset but requires problem-window
  bookkeeping (scores are only valid for post-cutoff windows); not yet
  collected.
- **Chinese benchmarks** (C-Eval, CMMLU, SuperCLUE): no public historical
  score series found without registration; components stay empty.
- Benchmark coverage: capability components currently draw on GPQA Diamond,
  MATH, AIME, SWE-bench Verified and LiveBench only.
- Download counters are cumulative levels with undocumented semantics on
  ModelScope and Ollama; only HF documents its rolling 30-day window.
- ModelScope/semantic verification pending; components stay empty rather than
  approximated.
