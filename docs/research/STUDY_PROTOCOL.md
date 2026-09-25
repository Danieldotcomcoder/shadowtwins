# Study protocol (preregistered-style) — Shadow Twins v1

Owner: P2. Written 2026-09-25 (UTC) before any model was run on any pack. P5 executes the pilot
and must label every analysis as **prespecified** (listed here) or **exploratory** (anything else).
Research diagnostics are separate from official ranked scores and never change them.

## 1. Central question

How effectively can LLMs optimize internal connectivity while preserving external projections
under a compact input budget?

Operationally: on the frozen ranked pack `shadowtwins-ranked-v1` (30 instances, 10 per tier),
what normalized score (`100·v/v*`, tier-equal mean) does a model reach under the standard
protocol (`st-protocol-1.0.0`, parser `st-parser-1.0.0`), and how does it compare with the
frozen baselines (no-op 0; uniform random legal edit 24.0; deterministic local search 75.9;
optimum 100 — `packs/shadowtwins-ranked-v1/reports/baselines.json`)?

## 2. Hypotheses (prespecified)

* **H1 (coordinated edits).** Conditional on validity, mean score is lower on T2 and T3
  (optimum needs ≥ 2 coordinated relocations, or defeats local search) than on T1.
  Test: paired within-model contrast T1 − mean(T2, T3) over instances, clustered bootstrap
  (§5). Direction prespecified: positive.
* **H2 (shadow constraint).** The dominant invalid category among completed answers is
  `silhouette_changed`, and validity is lower on instances with higher shadow rejection rate.
  Test: category proportions with bootstrap intervals; logistic association between validity and
  `shadow_rejection_rate` (instance-level, clustered).
* **H3 (ablation).** On the development-only ablation (§3), valid-answer rate rises when the
  silhouette rule is removed. The two conditions are scored against their **own** optima.
* **H4 (representation).** Scores on symmetry-transformed variants (§4) do not differ from the
  originals beyond sampling noise. A difference indicates sensitivity to coordinate presentation.

No hypothesis predicts a particular model ranking.

## 3. Full vs no-shadow ablation (development only)

* Pack: `shadowtwins-dev-v1` (30 development instances; never ranked).
* Conditions: standard prompt vs. the ablation prompt `st-protocol-1.0.0+noshadow`
  (`shadowtwins.ablation.render_prompt_no_shadow`, rule 2 removed, everything else identical).
* Scoring: standard evaluator for the full condition; `shadowtwins.ablation.evaluate_no_shadow`
  for the ablation, normalized by the certificate's `no_shadow.v_star`, never by `v*`.
* Report both conditions separately; ablation scores never enter leaderboards.

## 4. Equivalent-coordinate comparisons

For a development subset, apply one fixed non-identity cube symmetry per instance
(`shadowtwins.transforms.transform_instance`, IDs unchanged). Certified extrema are identical by
construction (tested). Variants are **correlated** with their originals: analyse as matched pairs
(difference per base instance) and never count variants as additional independent samples.

## 5. Analysis plan

* **Aggregation (official):** mean over repetitions within an instance → mean over instances within
  a tier → equal-weight mean over tiers. No best-of-n.
* **Uncertainty:** percentile bootstrap, 2,000 resamples, seed 20260925, resampling instances with
  replacement **within each tier** (stratified). Repetitions of an instance stay together (cluster).
  Symmetry variants stay with their base instance (cluster). Report 95% intervals.
* **Model comparisons:** paired by instance (same pack), bootstrap of the per-instance difference,
  stratified by tier.
* **Validity:** valid-answer rate and mean score conditional on validity are reported alongside the
  headline score; invalid answers score 0 in the headline.
* **Baselines:** report every model next to the four baselines on the same aggregation.
* **Infrastructure failures** (transport, outage, unresolved rate limit) are not scores; a run with
  unresolved items has no official total.
* **Multiplicity:** four hypotheses; report all, no correction claimed, interpret as a pilot.

## 6. Sampling design and inference limits

Instances are drawn by a seeded generator and admitted by a frozen policy
(`docs/research/ADMISSION_POLICY.md`); intervals describe variation over *this* population of
admitted instances, not general spatial ability. 10 instances per tier is a starting target, not a
power calculation. The public pack may enter training data; release dates and versions are
recorded and no contamination resistance is claimed.

## 7. Pilot (executed by P5)

At least one small and one larger model, only with available credentials and an explicit spending
cap. Record model id, provider endpoint, requested and observed settings, costs, validity, raw and
normalized quality, baselines and intervals. Do not modify the frozen pack after seeing results;
any correction creates a new pack version. A poor result triggers diagnosis, not post-hoc scoring
changes.
