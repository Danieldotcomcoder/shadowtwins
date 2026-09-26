# Pilot report

**Status: NOT RUN — blocked on credentials.** No `OPENROUTER_API_KEY` was available in the
implementation environment, so no model has been evaluated. No LLM results exist for this
benchmark yet, and none are implied anywhere in this repository.

What is ready:

* `tools/pilot.py` runs the prespecified pilot (docs/research/STUDY_PROTOCOL.md §7): one small and
  one larger model on the frozen `shadowtwins-ranked-v1` Standard track, profile `standard`, a
  pinned endpoint per model (cheapest compatible endpoint unless given), and an explicit total cap
  split between the two runs. It prints the plan and sends nothing without `--yes`, and refuses a run
  whose worst case exceeds its share of the cap.
* Defaults: `meta-llama/llama-3.1-8b-instruct` (small) and `meta-llama/llama-3.3-70b-instruct`
  (larger). At catalog prices on 2026-09-25 the combined worst case is below $0.15.
* The tooling was exercised end to end with mock models (`--dry-run-mock`):
  `docs/reports/PILOT_DRY_RUN.md`. Those numbers are **not** model results.

To run it:

```bash
OPENROUTER_API_KEY=... uv run python tools/pilot.py --cap 2.00          # review the plan
OPENROUTER_API_KEY=... uv run python tools/pilot.py --cap 2.00 --yes    # run; rewrites this file
```

The run replaces this file with the prespecified tables (overall and tier scores with 95%
intervals, validity, quality if valid, optimal rate, the H1 tier contrast, H2 answer categories and
their association with shadow activity, baselines on the same pack) plus run facts (requested and
observed settings, providers, tokens, cost, latency). The frozen pack must not be modified after
the results are seen.
