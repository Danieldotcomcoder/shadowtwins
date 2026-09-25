# Admission, tier and selection policy — st-policy-1.0.0

Owner: P2. Frozen 2026-09-25 (UTC) after the development pilot in
`docs/reports/DEV_POOL_REPORT.md` and before any practice or ranked seed was generated. The git
history records the order: the commit that freezes this policy precedes the commit that adds
`packs/shadowtwins-practice-v1` and `packs/shadowtwins-ranked-v1`. Code: `src/shadowtwins/policy.py`;
machine-readable copy with hash: `packs/<pack>/policy.json`.

No model output is used anywhere in admission, tiering or selection.

## Admission (all must hold)

| Rule | Threshold | Why |
|---|---|---|
| Positive optimum with room for partial credit | `v* ≥ 2` | `v* = 0` is inadmissible by definition; `v* = 1` makes every score 0 or 100 |
| Partial credit | at least 1 legal objective level strictly between 0 and `v*` | avoid binary outcomes (spec §6) |
| Not trivially dense | `optimal / legal ≤ 0.25` | a uniform legal edit must not be optimal a quarter of the time |
| Shadow rule active | `shadow_rejection_rate ≥ 0.20` | at least a fifth of otherwise permitted edits must fail only on silhouettes |
| Shadow rule matters for the objective | `shadow_traps ≥ 1` | some edit reaching ≥ `v*` without the silhouette rule must be illegal with it |
| Compact | panel max ≤ 800 tokens (`st-tokpanel-1.0.0`) | spec §7 ceiling |

Definitions are in `src/shadowtwins/metrics.py`. Structural validity (connected solid, boundary
empty entrances, distinct cells) is checked before measurement.

The 20% activity floor removes shell-protected and shadow-irrelevant cases: in the development
pool, 56 of 683 positive-optimum candidates fell below it (median rejection rate 58%).

## Tiers

Difficulty varies by edit interaction and search structure, not prompt length (prompt sizes are
indistinguishable across tiers in the development pool: medians 653–659 tokens).

| Tier | Budget | Rule |
|---|---|---|
| T1 single relocation | 1 | admitted |
| T2 paired relocations | 2 | admitted and the optimum needs exactly 2 relocations |
| T3 coordinated search | 3 | admitted and (the optimum needs 3 relocations, or the deterministic local search baseline `st-ls-1.0.0` does not reach the optimum) |

Development yields (admitted and matching the tier, per generated candidate): T1 8.2%, T2 15.0%,
T3 7.2%.

## Selection

* Seed ranges: development `1,000,000+`, practice `2,000,000+`, ranked `3,000,000+`, with tier
  offsets T1 `+0`, T2 `+100,000`, T3 `+200,000`. The ranges are disjoint.
* For each tier, seeds are consumed strictly in ascending order; the first candidates that are
  structurally valid, admitted, match the tier rule and have an unused geometry key are kept.
* Geometry key: the minimum canonical serialization of (occupancy, entrance set) over the 48 cube
  symmetries. A geometry used in any earlier accepted instance (development → practice → ranked)
  is never reused, whatever its editable list or budget.
* Targets: development 10 per tier (research only, never ranked), practice 3 per tier (9, unranked
  Quick Check and human practice), ranked 10 per tier (30). The Repeated Evaluation track reuses
  the 30 ranked instances with 3 repetitions each; it is not a separate pack.
* Every selected certificate must be reproduced by the independent verifier before the pack is
  written; the verification record is stored in each certificate.
* Counts are starting targets, not a statistical-power claim.

## Change control

Any change to a threshold, tier rule, seed range, generator or prompt protocol requires a new
policy version and new pack ids. Packs are never re-selected after model results exist.
