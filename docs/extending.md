# Adding a new source / benchmark / company / model

## Add a data source

1. Create `collectors/<source>.py` exposing `collect() -> list[dict]`.
2. Fetch from public APIs/endpoints only; respect rate limits and terms.
3. **Archive the raw response** with `collectors.base.archive_raw(source, payload)`
   - processing must be repeatable without refetching.
4. Return rows conforming to a standard schema (see `common.STANDARD_SCHEMAS`):
   - usage: `date, source_model_id, tokens[, estimated_spend]`
   - benchmarks: `date, benchmark, source_model_id, score[, rank]`
   - downloads: `date, source_model_id, downloads`
   - model_metadata: `date, source_model_id, company_name, weights_status[, release_date]`
   (set `source` via `collect.py`; just return `"_dataset": "<schema>"` on rows)
5. Register in `collect.py`: add to `ALL_SOURCES` and the dispatcher.
6. Document limitations in `docs/methodology.md` (counter semantics, history
   depth, known gaps), and `.env.example` if the source needs a key.
   If a metric is unreliable, say so - do not proxy it.

Rules:
- Idempotent: rerunning must not duplicate observations (keyed by date+id).
- One failing source must not stop the others (collect.py isolates failures
  and reports stale sources at the end).
- Never put secrets in the repo; read keys from environment variables.

## Add a benchmark

1. Add a row to `config/benchmarks.csv` (id, name, category, preferred source).
2. Verify version/edition and historical coverage **before** wiring data;
   document the choice (avoid mixing versions / double counting).
3. Regenerate the weights workbook: `python scripts/build_weights_template.py`
   (this appends capability components for the new benchmark).
4. Map the source's model ids for this benchmark in `config/model_mapping.csv`.
5. `python process.py` and check the new components appear with sensible
   coverage.

## Add a company

1. Add to `config/companies.csv`: `company_id,company_name,hq_country,geography`.
   Geography must be one of US / China / EU / RoW (derive from
   `country_geography.csv`).
2. If the HQ country is new, add it to `config/country_geography.csv`.

## Add a model

1. Add to `config/models.csv`: `model_id,model_name,company_id,weights_status`
   (`open` | `closed` | `unknown`; open weights ≠ open source).
2. Add mappings for every source where the model appears
   (`config/model_mapping.csv`: `source,source_model_id,model_id`).
   - Prefer exact source identifiers; add variants (`:free` etc.) as needed.
3. Unmapped ids are logged to `data/unmatched_review.csv` after each run -
   resolve them by filling `model_id` there, then move confirmed rows into
   `model_mapping.csv`.
4. Rerun `python process.py` (no recollection needed).

## Weights experiments

Edit only the `weight` column of the `Weights` sheet in
`config/weights.xlsx`, then rerun `python process.py`. Weights are
auto-normalised; 0 disables a component; missing components are excluded (not
zero-filled) and remaining weights renormalised; coverage is reported.
