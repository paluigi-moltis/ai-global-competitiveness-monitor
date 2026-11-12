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

### Estimated spending (EXPERIMENTAL, zero default weight)

Estimated spend cannot be reconstructed accurately from total tokens. If
implemented it must use:

```
estimated_spend = tokens × (input_share × input_price + output_share × output_price)
```

with an explicitly documented input/output mix assumption and **archived
historical prices** where available (otherwise labelled "current prices").
Zero weight by default until reliability is assessed.

### Downloads

- **Hugging Face**: the public `downloads` field is a **cumulative rolling
  30-day counter**, not a daily increment. Only levels are collected; daily
  changes must be derived in processing with explicit documentation of the
  counter semantics.
- **ModelScope**: counter semantics to be verified before any change
  computation (Phase 2+).
- **Ollama**: pull counts are shown for some models on the library page;
  availability and semantics unverified (Phase 2+).
- **Platform separation**: geographical shares are computed within each
  platform. Raw counts are never summed across platforms: counters measure
  different things over different windows.

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

## Known data gaps (documented, not fabricated)

- No reliable historical daily usage data before OpenRouter's dataset start
  (2025-01-01).
- Spending estimates absent until prices are archived.
- Ollama pulls unavailable as a reliable comparable metric (as of writing).
- Several Chinese-benchmark series lack systematic non-Chinese-model history.
- ModelScope/semantic verification pending; components stay empty rather than
  approximated.
