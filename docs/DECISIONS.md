# Decision log

Append-only. Each entry: date, owner, decision, reason, affected prompts, evidence.

## 2026-09-26 — P1 — Repository location and integration branch
* **Decision:** The repository is `C:\Users\danie\Desktop\System\llmbenchmarks` (local git, no remote
  yet). Integration branch: `main`. Each prompt works on `p<N>/<topic>` and merges into `main`
  with `--no-ff`.
* **Reason:** This is the authorized workspace that contains the Project Hub export; no repository
  existed.
* **Affected:** P1–P5. **Evidence:** `git log --graph`.

## 2026-09-26 — P1 — Coordinate convention and flat index
* **Decision:** `x` column (left→right), `y` row (first printed row is y=0), `z` layer (0 bottom),
  index `x + 4y + 16z`; silhouette arrays stored `rows[v][u]` with (u,v) = (y,z), (x,z), (x,y)
  for views along x, y, z. See `docs/FORMAL_RULES.md` §1, §4.
* **Affected:** P2 prompt text, P4 rendering. **Evidence:** `tests/shadowtwins/test_grid.py`.

## 2026-09-26 — P1 — Evaluation precedence and parser strictness
* **Decision:** Category precedence and parser rules as in `docs/FORMAL_RULES.md` §6–7
  (`st-parser-1.0.0`, `st-eval-1.0.0`). Booleans and fractional numbers are never IDs; one object or
  one fence only; duplicate keys are ambiguous and rejected; refusal detection is a versioned phrase
  list applied only to text containing no `{`.
* **Reason:** Spec §4 and §7 require strict, versioned, never-repairing parsing with separate
  refusal/truncation categories.
* **Affected:** P3 (stores categories), P4 (displays them).
  **Evidence:** `tests/shadowtwins/test_parser.py`, `test_evaluate.py`.

## 2026-09-26 — P1 — Single user message
* **Decision:** Each instance is one user message (no system message) so every provider receives
  identical authored text. Token measurement counts that text (P2).
* **Affected:** P2, P3.

## 2026-09-26 — P1 — Certificates carry a no-shadow ablation
* **Decision:** Certificates include the optimum and histogram of the same edit space without the
  silhouette rule (`core.no_shadow`). It is a research diagnostic (spec §14) and never used for
  scores.
* **Affected:** P2 research design.

## 2026-09-25 — P2 — Frozen tokenizer panel st-tokpanel-1.0.0
* **Decision:** Ceiling 800 tokens over the single user message under seven tokenizers: tiktoken
  o200k_base and cl100k_base; Hugging Face tokenizer.json for Llama 3.1 (NousResearch mirror), Qwen 2.5,
  DeepSeek V3, Mistral Nemo, Phi-3.5, each pinned by revision and sha256. Gemma is gated and excluded;
  Anthropic/Google tokenizers are not public. No chat-template tokens are counted.
* **Affected:** P3 (records provider usage separately), P5. **Evidence:** `src/shadowtwins/tokens.py`.

## 2026-09-25 — P2 — Admission/tier policy st-policy-1.0.0 and packs v1
* **Decision:** Thresholds, tiers (T1 b=1; T2 b=2 & optimum needs 2 moves; T3 b=3 & optimum needs 3
  moves or defeats local search), disjoint seed ranges and geometry-level duplicate rule as in
  `docs/research/ADMISSION_POLICY.md`; frozen in commit `3c361ba` before practice/ranked generation.
  Packs: `shadowtwins-dev-v1` (research), `shadowtwins-practice-v1` (9), `shadowtwins-ranked-v1` (30).
* **Affected:** P3 (pack loading, modes), P4 (practice mode), P5 (pilot).
* **Evidence:** `docs/reports/DEV_POOL_REPORT.md`, `docs/reports/PACKS_V1.md`, `tests/shadowtwins/test_packs.py`.

## 2026-09-25 — P3 — Run-level contract extensions
* **Decision:** `RunCreate` extends P1's `RunSpec` with optional `pack_id`; `provider` holds the
  OpenRouter endpoint tag used for `provider.order`. Profiles `prof-standard-1`,
  `prof-reasoning-low-1`, `prof-reasoning-high-1`; aggregation `agg-1.0.0`; listing policy `lb-1.0.0`;
  API `api-1.0.0` (`contracts/openapi.json`). The benchmark interface gained two optional hooks
  (`reference_answer`, `sample_answer`) used only by the mock provider, never for scoring.
* **Affected:** P4 (typed client), P5. **Evidence:** `docs/BACKEND.md`, `tests/benchserver/*`.

## 2026-09-26 — P5 — Release packaging and pilot defaults
* **Decision:** One image `shadowtwins:0.1.0` (Python 3.12.13-slim with a Node 22.16 build stage, uv
  0.11.29, tini, uid 10001, port 8000, volume /data, `benchserver supervise`). Container auth defaults
  to `token` when `ST_OPERATOR_TOKEN` is set. Public catalog requests never carry the API key. Pilot
  defaults: Llama 3.1 8B (small) and Llama 3.3 70B (larger), Standard track, cheapest compatible
  pinned endpoint, total cap required.
* **Affected:** operators; P5 pilot. **Evidence:** `docs/reports/CONTAINER_ACCEPTANCE.md`,
  `docs/reports/RELEASE_CHECK.md`.

## 2026-09-27 — P5 — Rate-limit policy, fresh retry budgets, login link
* **Decision:** 429s use their own schedule (6 attempts, 15 s → 120 s) and a run-wide dispatch
  cooldown; explicit operator requeues reset the retry budget (`jobs.retry_base`, migration 0002).
  The operator token is remembered in localStorage and can be passed once via a URL fragment
  (`#token=`), which is never sent to the server. Scoring, parser and packs are unchanged.
* **Reason:** the first live run (free `google/gemma-4-31b-it:free`, 2026-09-27) hit per-minute
  free-tier limits; the 2/4/8 s schedule exhausted retries within seconds, and a manual retry
  inherited the exhausted budget.
* **Affected:** operators, P5. **Evidence:** `test_rate_limits_back_off_the_whole_run`,
  `test_explicit_retry_starts_a_fresh_retry_budget`, `frontend/src/api/client.test.ts`.

## 2026-09-27 — Open question for the owner — strict answer format vs. reasoning in the answer
* **Observation:** in the first live run, all three answers from `google/gemma-4-31b-it:free`
  reasoned in prose and ended with a fenced JSON answer; under `st-parser-1.0.0` (spec §7: reject
  prose-wrapped answers) they score `malformed_json`.
* **Status:** unchanged. Changing this would be a scoring change requiring a new parser version
  and a decision; options are keeping the strict track, or adding a separate, clearly labelled
  lenient track that accepts a final fenced JSON block. **Owner decision needed.**

## 2026-09-27 — P5 calibration — Output budgets for thinking models (`prof-*-2`)
* **Decision:** profile output budgets become ceilings that should not bind: standard 65,536,
  reasoning-low 65,536, reasoning-high 131,072 (reasoning included), each capped at the model's own
  max completion tokens / context, with a floor of 8,192 below which the profile is incompatible.
  Profiles are versioned `prof-*-2`; the budget actually sent is recorded per run. The typical cost
  estimate assumes 16,000 output tokens per call for reasoning-capable models (1,500 otherwise), and
  the HTTP read timeout default rises to 3,600 s. Parser, scoring and packs unchanged.
* **Reason:** the first run on a thinking model (`nvidia/nemotron-3-ultra-550b-a55b:free`, default
  effort high) hit the 8,192 cap while still reasoning on every item (4,880–5,621 reasoning tokens,
  `finish_reason=length`, no answer written), so v1 measured the cap, not the model. The spec
  leaves profile values to calibration (§ step 6), which the live pilot was meant to perform.
* **Affected:** all new runs; results of `prof-*-1` runs are not comparable with `prof-*-2` and are
  separated by profile version. **Evidence:** attempts 50–51 of `run_20260927_160658_a517a3`;
  `test_profile_compatibility_uses_real_limits`.

## 2026-09-29 — P5 — Groq as a second provider
* **Decision:** add a Groq adapter (`GROQ_API_KEY`, `GROQ_PLAN=free|developer`). Groq models are
  namespaced `groq:<id>` because their ids collide with OpenRouter's; the provider is chosen by that
  prefix. Groq has no endpoints or fallbacks, so its runs can be ranked. Pricing is $0 on the free
  plan and the list price on the developer plan. Non-GPT-OSS reasoning models are sent
  `reasoning_format: "parsed"` so reasoning never lands in the answer. A 429's Retry-After is now
  honoured up to 24 h (was capped at 10 min), so a daily quota pauses a run until the reset. The
  OpenRouter adapter's HTTP/error/response handling moved to a shared `openai_compat` base
  (behaviour unchanged). Parser, scoring, packs and profiles unchanged.
* **Reason:** the owner asked for Groq support on its free plan. Checked live on 2026-09-29: the
  free plan limits GPT-OSS/Qwen to 8,000 tokens/min and 200,000/day, yet accepted a single
  `max_completion_tokens = 65,536` request and returned a 33,562-token answer (finish `stop`), so
  profile budgets need no Groq-specific cap; Qwen 3.8 returns `<think>` text inside `content` unless
  asked otherwise.
* **Affected:** operators, catalog, runner. **Evidence:** `tests/benchserver/test_groq.py`.
