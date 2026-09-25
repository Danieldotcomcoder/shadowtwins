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
