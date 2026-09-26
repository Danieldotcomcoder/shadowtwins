# Pilot tooling dry run (mock provider — not model results)

Generated 2026-09-26T05:05:57Z · pack `shadowtwins-ranked-v1` · Standard track · profile `standard` · cap $2.00, spent $0.0239 (within cap).

These numbers come from deterministic mock models and only demonstrate that the pilot tooling, runner, analysis and report generation work end to end. They say nothing about any LLM.

## Prespecified results

| Model | Endpoint | State | Overall (95% CI) | T1 | T2 | T3 | Valid | If valid | Optimal | H1: T1 − mean(T2,T3) (95% CI) |
|---|---|---|---|---|---|---|---|---|---|---|
| mock/random | mock-endpoint | completed | 6.6 [1.1, 13.6] | 6.7 | 5.7 | 7.3 | 60% | 11.0 | 0% | 0.1 [-11.7, 16.7] |
| mock/optimal | mock-endpoint | completed | 100.0 [100.0, 100.0] | 100.0 | 100.0 | 100.0 | 100% | 100.0 | 100% | 0.0 [0.0, 0.0] |

Baselines on the same pack and aggregation: no-op 0.0, uniform random legal edit 24.0, uniform random candidate 8.0, local search 75.9, optimum 100.0.

### Answer categories (H2)

* **mock/random**: valid 18, silhouette_changed 11, solid_disconnected 1. Correlation of validity with shadow rejection rate: -0.17 (n = 30).
* **mock/optimal**: valid 30. Correlation of validity with shadow rejection rate: — (n = 30).

## Run facts

| Model | Requested settings | Observed provider / model | Tokens in / out / reasoning | Cost | Mean latency |
|---|---|---|---|---|---|
| mock/random | `{"max_tokens": 8192, "temperature": 0.0}` | Mock / mock/random | 11549 / 180 / 0 | $0.0119 | 5 ms |
| mock/optimal | `{"max_tokens": 8192, "temperature": 0.0}` | Mock / mock/optimal | 11549 / 206 / 0 | $0.0120 | 5 ms |

## Exploratory notes

None recorded automatically. Anything added below this line is exploratory, not prespecified.

## Limitations

* Two models, one repetition, 30 instances: a pilot, not a ranking. Intervals describe this pack's sampling design only.
* The pack is public; contamination resistance is not claimed.
* Provider-side settings not observable through the API are not reported as facts.
