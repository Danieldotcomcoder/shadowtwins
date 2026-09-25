"""Official aggregation and uncertainty (owned by P3; used identically online and offline).

* Repetitions are averaged within an instance (never best-of-n), instances within a tier, and
  tiers are weighted equally. With one benchmark in the suite, overall = Shadow Twins.
* An **official** total exists only when every scheduled item has a completed, evaluated answer.
  Failed, uncertain, cancelled or pending items never disappear from the denominator: they make
  the run incomplete, and only a clearly labelled *provisional* mean over completed items is shown.
* Intervals: percentile bootstrap resampling instances with replacement within each tier
  (stratified); an instance's repetitions stay together (cluster). Fixed seed, full precision.
"""

from __future__ import annotations

import random
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20260925
AGGREGATION_VERSION = "agg-1.0.0"


@dataclass(frozen=True)
class ScoredItem:
    instance_id: str
    tier: str
    repetition: int
    state: str  # job state; only "completed" items carry a score
    score: float | None = None
    valid: bool | None = None
    optimal: bool | None = None
    category: str | None = None


def _mean(xs: Iterable[float]) -> float:
    return statistics.fmean(list(xs))


def instance_means(items: list[ScoredItem]) -> dict[str, dict[str, float]]:
    """tier -> instance -> mean score over completed repetitions."""
    acc: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for it in items:
        if it.state == "completed" and it.score is not None:
            acc[it.tier][it.instance_id].append(it.score)
    return {t: {i: _mean(v) for i, v in d.items()} for t, d in acc.items()}


def overall_from_means(means: dict[str, dict[str, float]]) -> tuple[float | None, dict[str, float]]:
    tiers = {t: _mean(d.values()) for t, d in sorted(means.items()) if d}
    return (_mean(tiers.values()) if tiers else None), tiers


def bootstrap_interval(
    means: dict[str, dict[str, float]], n: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED,
    level: float = 0.95,
) -> tuple[float, float] | None:
    tiers = {t: list(d.values()) for t, d in sorted(means.items()) if d}
    if not tiers:
        return None
    rng = random.Random(seed)
    stats = []
    for _ in range(n):
        tier_means = []
        for vals in tiers.values():
            k = len(vals)
            tier_means.append(sum(vals[rng.randrange(k)] for _ in range(k)) / k)
        stats.append(sum(tier_means) / len(tier_means))
    stats.sort()
    lo_i = int((1 - level) / 2 * (n - 1) + 0.5)
    hi_i = int((1 + level) / 2 * (n - 1) + 0.5)
    return stats[lo_i], stats[hi_i]


def aggregate(items: list[ScoredItem], with_interval: bool = True) -> dict[str, Any]:
    scheduled = len(items)
    states = Counter(it.state for it in items)
    completed = [it for it in items if it.state == "completed"]
    official = scheduled > 0 and len(completed) == scheduled
    means = instance_means(items)
    overall, tiers = overall_from_means(means)
    valid = [it for it in completed if it.valid]
    interval = bootstrap_interval(means) if with_interval and completed else None
    return {
        "aggregation_version": AGGREGATION_VERSION,
        "scheduled": scheduled,
        "completed": len(completed),
        "states": dict(states),
        "official": official,
        "overall": overall if official else None,
        "provisional_overall": overall,
        "tiers": tiers,
        "interval_95": list(interval) if interval else None,
        "valid_rate": len(valid) / len(completed) if completed else None,
        "conditional_quality": _mean(it.score for it in valid if it.score is not None) if valid else None,
        "optimal_rate": sum(1 for it in completed if it.optimal) / len(completed) if completed else None,
        "categories": dict(Counter(it.category or "valid" for it in completed)),
        "instances": sum(len(d) for d in means.values()),
    }
