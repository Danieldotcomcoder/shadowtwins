"""Baselines (P2): no-op, uniform random legal edit, deterministic local search, exact optimum.

* **No-op** is always legal and scores 0.
* **Uniform random legal edit** is reported exactly from the certificate histogram (expected score
  and probability of an optimum), plus a seeded sample for distributions. A second, harsher
  reference draws uniformly from all *enumerated* candidates, where illegal draws score 0.
* **Local search** (``st-ls-1.0.0``) is deterministic steepest ascent over legal edits starting
  from the no-op. Neighbours of an edit: add one relocation pair (if below budget), replace one
  removed ID, replace one added ID, or drop one (removed, added) pair; they are generated in a
  fixed lexicographic order. Every neighbour evaluated (legal or not, cached or not) consumes one
  unit of the evaluation budget (default 400). It moves to the best strictly improving legal
  neighbour and stops at a local optimum or when the budget runs out.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import dataclass

from . import grid
from .contracts import ShadowTwinsCertificate
from .engine import Compiled, apply_ids, entrance_labels, pair_changes

LOCAL_SEARCH_VERSION = "st-ls-1.0.0"
LOCAL_SEARCH_BUDGET = 400

Edit = tuple[tuple[int, ...], tuple[int, ...]]


def legal_value(c: Compiled, edit: Edit) -> int | None:
    final = apply_ids(c, edit[0], edit[1])
    if grid.silhouette_keys(final) != c.sil or not grid.is_connected(final):
        return None
    o, cl = pair_changes(c.labels, entrance_labels(final, c.entrances))
    return o + cl


def _neighbours(c: Compiled, edit: Edit) -> Iterator[Edit]:
    rm, ad = edit
    free_s = [k for k in c.solid_ids if k not in rm]
    free_e = [k for k in c.empty_ids if k not in ad]
    if len(rm) < c.budget:
        for s in free_s:
            for e in free_e:
                yield tuple(sorted((*rm, s))), tuple(sorted((*ad, e)))
    for i in range(len(rm)):
        for s in free_s:
            yield tuple(sorted((*rm[:i], *rm[i + 1:], s))), ad
    for j in range(len(ad)):
        for e in free_e:
            yield rm, tuple(sorted((*ad[:j], *ad[j + 1:], e)))
    for i in range(len(rm)):
        for j in range(len(ad)):
            yield rm[:i] + rm[i + 1:], ad[:j] + ad[j + 1:]


@dataclass
class LocalSearchResult:
    edit: Edit
    objective: int
    evaluations: int
    steps: int
    stopped_by_budget: bool


def local_search(c: Compiled, budget: int = LOCAL_SEARCH_BUDGET) -> LocalSearchResult:
    cur: Edit = ((), ())
    cur_v = 0
    evals = steps = 0
    cache: dict[Edit, int | None] = {cur: 0}
    while True:
        best: tuple[int, Edit] | None = None
        exhausted = False
        for nb in _neighbours(c, cur):
            if evals >= budget:
                exhausted = True
                break
            evals += 1
            if nb not in cache:
                cache[nb] = legal_value(c, nb)
            v = cache[nb]
            if v is not None and v > cur_v and (best is None or v > best[0]):
                best = (v, nb)
        if best is not None:
            cur_v, cur = best
            steps += 1
        if best is None or exhausted:
            return LocalSearchResult(cur, cur_v, evals, steps, exhausted)


def random_legal_expectation(cert: ShadowTwinsCertificate) -> dict[str, float]:
    core = cert.core
    v_star = core.v_star
    legal_mean = sum(int(v) * n for v, n in core.histogram.items()) / core.legal_count
    return {
        "random_legal_expected_score": 100.0 * legal_mean / v_star if v_star else 0.0,
        "random_legal_optimum_probability": core.optimal_count / core.legal_count,
        "random_candidate_expected_score": (
            100.0 * sum(int(v) * n for v, n in core.histogram.items()) / core.enumerated_count / v_star
            if v_star else 0.0),
        "random_candidate_valid_probability": core.legal_count / core.enumerated_count,
    }


def random_legal_sample(cert: ShadowTwinsCertificate, n: int, seed: int) -> list[float]:
    """Scores of ``n`` uniform draws from the certified legal set (via its histogram)."""
    core = cert.core
    rng = random.Random(seed)
    values = [int(v) for v in core.histogram]
    weights = [core.histogram[str(v)] for v in values]
    return [100.0 * v / core.v_star for v in rng.choices(values, weights=weights, k=n)]
