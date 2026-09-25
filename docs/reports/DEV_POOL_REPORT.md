# Development pool report (st-gen-1.0.0)

Every candidate in the development seed range was generated, certified exhaustively and measured, with no filtering. Practice and ranked seed ranges were **not** generated before the admission policy below was frozen. No model was run.

Source data: `docs/reports/data/dev_scan_v1.jsonl.gz` (1200 candidates). Reproduce: `uv run --extra research python tools/p2_pipeline.py dev-scan --n 400` then `dev-report`.

Quantiles are min / q1 / median / q3 / max.


## Budget 1 (candidates for T1, single relocation)

* Candidates: 400; structurally invalid draws: 19; `v* = 0`: 165; `v* > 0`: 216
* Admitted under the frozen policy: 33 (8.2% of candidates); also matching the T1 rule: 33 (8.2%)
* Admission failures among `v* > 0` (a candidate can fail several): `no_partial_credit` 154, `no_shadow_traps` 39, `optimum_too_dense` 34, `shadow_inactive` 34, `v_star_below_min` 12
* Shadow constraint binding (no-shadow optimum > v*): 63 of 216; with at least one shadow trap: 177 of 216
* Minimum relocations needed for the optimum: 1: 216
* Local search reaches the optimum: 216 of 216

| metric (v* > 0) | min / q1 / median / q3 / max | admitted |
|---|---|---|
| v* | 1 / 4 / 6 / 8 / 19 | 2 / 6 / 8 / 10 / 19 |
| entrance pairs | 10 / 15 / 21 / 28 / 28 | 10 / 15 / 21 / 28 / 28 |
| legal density | 0.162 / 0.426 / 0.549 / 0.673 / 1 | 0.273 / 0.451 / 0.525 / 0.636 / 0.781 |
| optimum density | 0.0137 / 0.0968 / 0.149 / 0.214 / 0.875 | 0.0175 / 0.0526 / 0.1 / 0.156 / 0.231 |
| shadow rejection rate | 0 / 0.262 / 0.395 / 0.525 / 0.818 | 0.219 / 0.345 / 0.403 / 0.525 / 0.688 |
| shadow traps | 0 / 1 / 4 / 9 / 33 | 1 / 1 / 3 / 7 / 17 |
| random legal expected score | 1.67 / 13.2 / 19 / 25.5 / 87.5 | 11.4 / 18.5 / 22.7 / 28.6 / 51.6 |
| random candidate expected score | 1.1 / 7.27 / 9.51 / 14.1 / 43.4 | 4.76 / 10.1 / 11 / 14.6 / 24.4 |
| local search score | 100 / 100 / 100 / 100 / 100 | 100 / 100 / 100 / 100 / 100 |
| prompt tokens (panel max) | 603 / 643 / 659 / 673 / 707 | 613 / 647 / 659 / 671 / 699 |
| certification ms | 1.31 / 2.92 / 3.98 / 5.01 / 8.95 | 1.55 / 3.35 / 4.09 / 5.39 / 7.26 |

Partial-credit levels strictly between 0 and v*: 0: 154, 1: 21, 2: 28, 3: 7, 4: 3, 5: 2, 7: 1


## Budget 2 (candidates for T2, paired relocations)

* Candidates: 400; structurally invalid draws: 32; `v* = 0`: 141; `v* > 0`: 227
* Admitted under the frozen policy: 84 (21.0% of candidates); also matching the T2 rule: 60 (15.0%)
* Admission failures among `v* > 0` (a candidate can fail several): `no_partial_credit` 121, `optimum_too_dense` 62, `no_shadow_traps` 18, `shadow_inactive` 11, `v_star_below_min` 3
* Shadow constraint binding (no-shadow optimum > v*): 109 of 227; with at least one shadow trap: 209 of 227
* Minimum relocations needed for the optimum: 1: 129, 2: 98
* Local search reaches the optimum: 178 of 227

| metric (v* > 0) | min / q1 / median / q3 / max | admitted |
|---|---|---|
| v* | 1 / 4 / 6 / 9 / 21 | 2 / 6 / 8 / 12 / 21 |
| entrance pairs | 10 / 10 / 21 / 28 / 28 | 10 / 15 / 21 / 21 / 28 |
| legal density | 0.0192 / 0.181 / 0.29 / 0.476 / 1 | 0.052 / 0.196 / 0.302 / 0.422 / 0.784 |
| optimum density | 0.00158 / 0.0417 / 0.127 / 0.271 / 0.889 | 0.00158 / 0.0163 / 0.0463 / 0.109 / 0.247 |
| shadow rejection rate | 0 / 0.424 / 0.63 / 0.759 / 0.98 | 0.216 / 0.465 / 0.623 / 0.744 / 0.942 |
| shadow traps | 0 / 14 / 69 / 188 / 949 | 1 / 9 / 42 / 100 / 768 |
| random legal expected score | 1.1 / 15.4 / 26 / 40.1 / 88.9 | 1.39 / 18 / 27.3 / 39.3 / 75.2 |
| random candidate expected score | 0.218 / 3.76 / 6.85 / 12.2 / 37.2 | 0.489 / 4.41 / 7.22 / 12 / 32.1 |
| local search score | 0 / 100 / 100 / 100 / 100 | 0 / 100 / 100 / 100 / 100 |
| prompt tokens (panel max) | 603 / 639 / 653 / 671 / 707 | 603 / 643 / 663 / 677 / 707 |
| certification ms | 6.67 / 30.3 / 45.5 / 72.7 / 162 | 14.2 / 34.6 / 54.5 / 85.2 / 142 |

Partial-credit levels strictly between 0 and v*: 0: 121, 1: 35, 2: 44, 3: 8, 4: 11, 5: 5, 6: 1, 7: 1, 8: 1


## Budget 3 (candidates for T3, coordinated search)

* Candidates: 400; structurally invalid draws: 26; `v* = 0`: 134; `v* > 0`: 240
* Admitted under the frozen policy: 91 (22.8% of candidates); also matching the T3 rule: 29 (7.2%)
* Admission failures among `v* > 0` (a candidate can fail several): `no_partial_credit` 122, `optimum_too_dense` 105, `shadow_inactive` 11, `no_shadow_traps` 9, `v_star_below_min` 3
* Shadow constraint binding (no-shadow optimum > v*): 123 of 240; with at least one shadow trap: 231 of 240
* Minimum relocations needed for the optimum: 1: 131, 2: 92, 3: 17
* Local search reaches the optimum: 189 of 240

| metric (v* > 0) | min / q1 / median / q3 / max | admitted |
|---|---|---|
| v* | 1 / 5 / 6 / 11 / 23 | 3 / 7 / 10 / 13 / 23 |
| entrance pairs | 10 / 15 / 21 / 28 / 28 | 10 / 15 / 21 / 28 / 28 |
| legal density | 0.00387 / 0.095 / 0.189 / 0.319 / 1 | 0.0134 / 0.113 / 0.201 / 0.353 / 0.734 |
| optimum density | 0.000528 / 0.0667 / 0.185 / 0.425 / 0.947 | 0.000528 / 0.0291 / 0.0667 / 0.115 / 0.226 |
| shadow rejection rate | 0 / 0.599 / 0.774 / 0.879 / 0.996 | 0.221 / 0.509 / 0.73 / 0.853 / 0.984 |
| shadow traps | 0 / 140 / 443 / 1.2e+03 / 8.1e+03 | 3 / 64 / 185 / 504 / 3.08e+03 |
| random legal expected score | 1.16 / 24 / 38.2 / 51.8 / 94.7 | 5.24 / 24 / 33.3 / 43.9 / 73.7 |
| random candidate expected score | 0.00605 / 2.43 / 6.49 / 11.7 / 65.7 | 0.445 / 3 / 6.2 / 11 / 32.5 |
| local search score | 0 / 100 / 100 / 100 / 100 | 0 / 100 / 100 / 100 / 100 |
| prompt tokens (panel max) | 603 / 641 / 659 / 671 / 699 | 603 / 649 / 659 / 677 / 699 |
| certification ms | 22 / 123 / 207 / 350 / 1.06e+03 | 35.6 / 138 / 227 / 427 / 984 |

Partial-credit levels strictly between 0 and v*: 0: 122, 1: 20, 2: 59, 3: 12, 4: 11, 5: 7, 6: 7, 7: 1, 11: 1


## Shadow activity across the pool

Across 683 candidates with `v* > 0`, the silhouette rule rejected a median 58.3% of otherwise permitted edits; 56 candidates fell below the 20% activity floor and are excluded as shell-protected or shadow-irrelevant. Shadow preservation is therefore an active constraint in the admitted population, not a vacuous one.


## Frozen policy

```json
{
  "policy_version": "st-policy-1.0.0",
  "generator_version": "st-gen-1.0.0",
  "admission": {
    "min_v_star": 2,
    "min_partial_levels": 1,
    "max_optimum_density": 0.25,
    "min_shadow_rejection_rate": 0.2,
    "min_shadow_traps": 1,
    "max_tokens": 800,
    "token_panel": "st-tokpanel-1.0.0"
  },
  "tiers": [
    {
      "id": "T1",
      "name": "single relocation",
      "budget": 1,
      "rule": "admitted with budget 1"
    },
    {
      "id": "T2",
      "name": "paired relocations",
      "budget": 2,
      "rule": "admitted with budget 2 and the optimum needs exactly 2 relocations"
    },
    {
      "id": "T3",
      "name": "coordinated search",
      "budget": 3,
      "rule": "admitted with budget 3 and (the optimum needs 3 relocations or the deterministic local search baseline does not reach the optimum)"
    }
  ],
  "selection": {
    "seed_bases": {
      "development": 1000000,
      "practice": 2000000,
      "ranked": 3000000
    },
    "per_tier": {
      "development": 10,
      "practice": 3,
      "ranked": 10
    },
    "max_candidates_per_tier": 50000,
    "procedure": "For each tier, iterate seeds base + tier_offset + k for k = 0, 1, 2, ... with the tier's budget; keep a candidate when it is structurally valid, admitted, matches the tier rule and its geometry key (48-symmetry canonical form of occupancy + entrance set) was not used by any earlier accepted instance in any split; stop at the per-tier target.",
    "tier_offsets": {
      "T1": 0,
      "T2": 100000,
      "T3": 200000
    }
  },
  "policy_hash": "sha256:372ada53017c81e58dfddf367b9e536bd62e48d805ee888e6ca2a466ce9b95b5"
}
```

