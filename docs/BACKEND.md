# Backend: API, durable runner and providers (P3)

The API contract is `contracts/openapi.json` (generated; `uv run benchserver export-openapi --check`
fails on drift). Interactive docs are served at `/api/docs`.

## Processes

| Command | Purpose |
|---|---|
| `benchserver migrate` | apply SQL migrations, then load shipped packs (hash-checked, never recertified) |
| `benchserver api` | FastAPI + compiled frontend on one origin (expects a migrated DB) |
| `benchserver worker` | durable worker (separate process) |
| `benchserver supervise` | container entrypoint: migrate → start API + worker → restart/stop them |
| `benchserver dev` | development: migrate + API with an embedded worker |

## Run lifecycle

```
create ──► active ──► completed        (every job completed and evaluated)
            │  ▲  └──► incomplete      (nothing left to dispatch; some failed/uncertain)
            │  │
            ├► paused ────────┘ resume (in-flight requests settle; no new dispatch)
            ├► budget_stopped ┘ resume (after raising the limit)
            └► cancelling ──► cancelled (unsent jobs cancelled; in-flight settle and are recorded)
```

Job states: `queued → leased → completed | retry_wait → (queued) | uncertain | failed`, plus
`cancelled`. Operator actions: `pause`, `resume`, `cancel`, `rerun_uncertain` (explicit, may be
charged again; logged), `retry_failed`, `set_spend_limit`.

## Durability and honesty rules

* Jobs exist in SQLite before any request. Leases are taken in `BEGIN IMMEDIATE` transactions and
  extended by worker heartbeats; a worker's leases are recovered when it stops or goes stale.
* Every attempt is recorded (`prepared → sent → response | failed | ambiguous | abandoned`).
  Recovery: never-sent → requeued; stored response → evaluated without a new request;
  sent-without-response → `uncertain` (rerun only by explicit operator action).
* Retries apply only to transport errors before sending, 5xx/408/provider-finish errors (4 attempts,
  2 s…60 s) and 429 rate limits (6 attempts, 15 s…120 s, honouring `Retry-After`, with a run-wide
  dispatch cooldown). Explicit operator requeues reset the retry budget (`jobs.retry_base`,
  migration 0002). A completed answer —
  valid, invalid, refused or truncated — is never retried. `401`/`402` pause the run; other 4xx
  fail the job.
* Exactly-once execution across OpenRouter is **not** claimed.

## Costs

Before dispatch the worker reserves a worst case per call: `(panel max tokens × 1.25 + 64) × prompt
price + output budget × max(completion, internal reasoning price) + request fee`. Dispatch stops
(`budget_stopped`) when `spent + reserved + next reservation` would exceed the limit. Reported
OpenRouter `usage.cost` replaces the reservation; if absent, cost is estimated from usage tokens
(`cost_source = estimated`); ambiguous attempts are charged their full reservation
(`reserved_uncertain`). Unknown pricing blocks a run unless the operator sets the explicit
unranked override. Cost and latency never enter quality scores.

## OpenRouter

* Catalog: `GET /models` (public) cached in `catalog_snapshots` (TTL 1 h; stale snapshot served on
  failure). Endpoints: `GET /models/{id}/endpoints`; the endpoint `tag` (e.g. `deepinfra/fp8`) is
  the pin value.
* Requests: prompt-requested JSON only (no tools, no `response_format`, no `models` fallback list),
  `provider = {order: [pin], allow_fallbacks: false, require_parameters: true}` when pinned.
* Recorded per attempt: request body (provider-neutral, no headers), generation id, reported
  provider and model, finish reasons, usage (incl. reasoning tokens), cost and latency. Reasoning
  text is not stored (only its length).
* Ranked eligibility requires: ranked pack, non-mock model, pinned endpoint, known pricing, a
  compatible profile, a completed run, and no response whose reported provider contradicts the pin.

## Profiles (`prof-*-2`)

| id | output budget (ceiling) | temperature | reasoning | requires |
|---|---|---|---|---|
| standard | 65,536 | 0 if supported | model default (not controlled) | — |
| reasoning-low | 65,536 | — | `effort: low` | `reasoning` |
| reasoning-high | 131,072 | — | `effort: high` | `reasoning` |

The output budget includes reasoning tokens and is a ceiling meant not to bind: a model (or pinned
endpoint) whose max completion tokens, or context minus the prompt, is lower gets its own maximum
instead. The budget actually sent is stored in the run's request template
(`params.max_tokens`; `settings.profile_max_tokens`, `settings.max_tokens_capped_by`) and used for reservations.
Profiles are incompatible only when that budget would fall below 8,192 tokens, or when a required
parameter or effort is not supported. Equal effort labels are **not** equal reasoning budgets
across models. `prof-*-1` (8,192 / 16,384 / 32,768, no capping) truncated thinking models and
remains only on runs created before 2026-09-27.

## Aggregation and leaderboard

`benchcore.aggregate` (`agg-1.0.0`): mean over repetitions within instance → mean within tier →
equal-weight mean over tiers; official total only when every scheduled job is completed; 95 %
percentile bootstrap (2,000 resamples, seed 20260925) stratified by tier with repetitions kept
together. Leaderboard policy `lb-1.0.0`: latest completed eligible run per (model, endpoint,
profile, track, pack hash, suite version) — never the best historical run; full history in model
detail. Suite 1 contains one benchmark, so overall = Shadow Twins.

## Security

* Credentials only from the environment; never logged (log filter), stored, exported or returned.
* Run controls require operator authorization: `ST_AUTH_MODE=token` (Bearer `ST_OPERATOR_TOKEN`),
  `local` (loopback clients only; default without a token), `readonly`, or `open` (explicit).
  Bearer tokens are not cookies, so no CSRF surface. Reads are public.
* 64 KiB request body limit; strict schemas (`StrictInt` IDs); parameterized SQL; model output is
  only returned as JSON data; CSP and `nosniff` headers; nothing executes model output.

## Data, backup and restore

SQLite in WAL mode at `$ST_DATA_DIR/shadowtwins.db`. `benchserver backup PATH` uses the online
backup API (consistent while running, includes WAL pages, integrity-checked). `benchserver restore
PATH` copies a verified backup into the live database through the same API (stop API and worker
first). Logs rotate at 5 MB × 3 under `$ST_DATA_DIR/logs`.

## Mock provider

`ST_ENABLE_MOCK_PROVIDER=1` adds `mock/*` test doubles (optimal, no-op, random, prose, refusal,
truncated, flaky 503, rate-limited 429, ambiguous timeout, slow, reasoner, unpriced, 400, 402).
Mock runs are labelled everywhere and can never be ranked or listed.
