# Known issues and limitations

## Observed in the first live run (2026-09-27)

* A free model (`google/gemma-4-31b-it:free`) wrote its reasoning as prose and ended with a fenced
  JSON answer; the strict parser scores that `malformed_json` (see the open question in
  `docs/DECISIONS.md`).
* Free models are throttled (per minute, per day, and upstream at the provider): 3 of 9 requests
  completed after retries. The account had no OpenRouter credits, so paid models cannot run yet.
* A thinking model (`nvidia/nemotron-3-ultra-550b-a55b:free`) was truncated on every item under the
  8,192-token `prof-standard-1` budget while still reasoning. Fixed by `prof-*-2` (see
  `docs/DECISIONS.md`). Free endpoints are also slow (~27 output tokens/s, so one long thinking
  answer can take 20–40 minutes) and occasionally end a response with a provider error, which is
  retried.

## Groq free plan (2026-09-29)

* Daily token limits (200,000 per model for GPT-OSS and Qwen) fit only a handful of thinking-model
  answers (15–30k tokens each), so a 9-item quick check spans two or more days; the run waits for
  the reset by itself. Groq's daily check counts the requested output budget: a request needs
  prompt + 65,536 tokens of daily headroom to start ("Used 163126, Requested 66164"), so roughly the
  last third of each day's quota cannot start a full-budget request. Observed on the first live
  run (gpt-oss-20b): scores 100 and 88.9, one invalid answer, one answer truncated at 65,536 tokens.
* Right after a long answer, Groq's per-minute limiter answers the next request with 429 and then
  413 "Request too large", both coded `rate_limit_exceeded`; both are treated as rate limits and
  waited out (the first live run had failed two items on the 413 before this was handled).
* Reasoning efforts per model family are hard-coded from Groq's documentation (the catalog only
  flags reasoning); a new reasoning family gets no effort check and is sent
  `reasoning_format: "parsed"`.

## Open release gates

* **Live pilot not run.** No OpenRouter key was available; see `docs/research/PILOT_REPORT.md`.
  Live completions through OpenRouter (as opposed to the live catalog, which was exercised) have not
  been observed end to end, so real-provider behaviour (reported provider names, usage/cost fields,
  finish reasons for specific models) is only covered by adapter tests against captured response
  shapes.
* **No independent review** of P1–P5 has been performed. Every handoff records self-review only.
* **Notion tracker not synchronized** (`docs/HUB_SYNC.md`).
* **CI workflow not yet executed on GitHub.** `.github/workflows/ci.yml` mirrors the local
  commands that were run; the repository has no remote.

## Benchmark

* Novelty is unconfirmed (`docs/research/RELATED_WORK.md`); the search was scoped, not systematic.
* T1 instances are solvable by an exhaustive single-move scan (the local-search baseline scores 100
  on T1); T1 difficulty rests on reasoning, not search.
* Partial credit is often coarse (median 2 intermediate objective levels per ranked instance),
  because entrance pairs change together when components split or merge.
* The pack is public and may enter training data; no contamination resistance is claimed.
* 10 instances per tier are a starting target, not a power calculation.

## Protocol and scoring

* The parser rejects prose around the JSON answer. Models that print reasoning into the answer
  text (rather than a separate reasoning channel) score `malformed_json` under the standard track;
  this is intentional, but it may penalise some providers' output formats.
* Refusal detection is a small English phrase list, applied only to text without `{`.
* Token counts exclude chat-template tokens, and closed tokenizers (Anthropic, Google) cannot be
  measured, so billed prompt tokens differ from the offline panel.
* Reasoning effort labels are requests; OpenRouter maps them per model, and equal labels do not
  mean equal reasoning budgets.

## Operations

* Exactly-once execution across OpenRouter is not claimed. A request lost mid-flight becomes
  *uncertain*, and rerunning it may be charged twice.
* The spending limit is enforced with conservative per-call reservations; provider billing can
  still differ slightly (template tokens, rounding).
* The reported provider is compared with the pinned endpoint by provider name; a pinned endpoint
  variant (quantization tag) is not independently observable in the response.
* `ST_AUTH_MODE=local` does not work for browsers talking to a container (requests are not from
  loopback); use `ST_OPERATOR_TOKEN`.
* On 2026-09-26 during development, a `taskkill /IM python.exe` used to stop a dev server may have
  closed other Python processes on the development machine; this does not affect the product.

## Frontend

* The three.js chunk is 1.16 MB (317 kB gzip); it is loaded lazily only on 3D pages.
* The automated accessibility gate excludes colour contrast (checked manually on the dark theme); a
  screen-reader walkthrough has not been done.
* Visual checks were run in Playwright Chromium with SwiftShader WebGL (desktop 1440×900 and
  Pixel 7 emulation), not on physical GPUs or Safari/Firefox.
