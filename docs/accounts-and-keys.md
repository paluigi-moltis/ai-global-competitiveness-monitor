# Accounts & API Keys Guide

Everything the pipeline needs from external services, and what to create
where. Keys live in a **`.env` file at the repo root** (copy
`.env.example` → `.env`); it is git-ignored and loaded automatically by
`collect.py` and `process.py`. Real environment variables take precedence
over `.env` values.

**TL;DR: only one account is required (OpenRouter). Everything else works
key-free today.**

| Service | Account needed? | Variable | Status |
|---|---|---|---|
| OpenRouter | **Yes — required** | `OPENROUTER_API_KEY` | collector implemented, blocked on key |
| Vercel AI Gateway | No | — | collecting |
| Epoch AI | No | — | collecting |
| LiveBench | No | — | collecting |
| Hugging Face | Optional | `HF_TOKEN` | collecting (token only lifts rate limits) |
| ModelScope | No | — | collecting |
| Ollama | No | — | collecting |
| LMArena | ✅ No account — official HF dataset, anonymous download | — | collecting |
| Artificial Analysis | Future | `ARTIFICIAL_ANALYSIS_API_KEY` | placeholder only |

---

## 1. OpenRouter — REQUIRED (adoption usage data)

The single most valuable keyed source: daily per-model token usage and
estimated spending across geographies, with history back to 2025-01-01
(dataset published under CC BY 4.0).

1. Go to <https://openrouter.ai> and sign in (Google/GitHub/email).
2. Open **Settings → Keys**: <https://openrouter.ai/settings/keys>.
3. Click **Create key** — any named key works; no credit or special scope
   needed for the data endpoints. Copy the key immediately (shown once,
   format `sk-or-v1-…`).
4. Save it in `.env`:

   ```
   OPENROUTER_API_KEY=sk-or-v1-your-key-here
   ```

5. Verify and collect:

   ```bash
   python collect.py --source openrouter
   ```

Limits: ~30 requests/minute, ~500/day — the collector stays far below
this. Free key, no card required.

## 2. Hugging Face — optional (rate limits only)

Downloads/metadata for open-weight models are collected today without a
token (public API). Only add a token if you hit anonymous rate limits
(`429` responses in the collect log).

1. Sign up at <https://huggingface.co/join> (or sign in).
2. **Settings → Access Tokens**: <https://huggingface.co/settings/tokens>.
3. Create a **fine-grained** token with **read** access only (no repos,
   no write). Format `hf_…`.
4. Save in `.env`:

   ```
   HF_TOKEN=hf_your-token-here
   ```

## 3. Arena (LMArena) — no account needed

The `lmarena.ai` API rejects unauthenticated clients (403), but Arena
publishes the **complete history of every leaderboard** as a public
Hugging Face dataset (announced April 2026, CC BY 4.0, not gated):
<https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset>. The
collector downloads the `text` subset's `full` split (Bradley-Terry
ratings, 2023-05 → today) anonymously — nothing to create or configure.

## 4. Artificial Analysis — future placeholder

If we later add their evaluations index: account at
<https://artificialanalysis.ai>, key from the dashboard, saved as
`ARTIFICIAL_ANALYSIS_API_KEY=…` in `.env`. **The API terms must be
reviewed before any collection starts** (their free tier may not permit
redistribution of derived indices). Nothing to do today.

---

## No account needed (working today)

| Source | What we pull | Notes |
|---|---|---|
| Vercel AI Gateway | daily token/spend shares | public CSV export, CC BY 4.0 |
| Epoch AI | GPQA / MATH / AIME / SWE-bench history | public zip, CC BY 4.0 |
| LiveBench | 11 historical leaderboard releases | public GitHub CSVs |
| ModelScope | download levels for 7 CN-platform repos | public per-repo API |
| Ollama | download counts for 10 models | public library pages |

## Managing the `.env` file

```bash
cd ~/coding/ai-global-competitiveness-monitor
cp .env.example .env      # first time only
$EDITOR .env              # paste keys
```

- `.env` is git-ignored — keys never reach the repository.
- Collectors read keys via `python-dotenv` at import time; rerun
  `collect.py` after editing.
- All collectors are idempotent (append by unique key, history preserved),
  so rerunning after adding a key backfills only that source.
