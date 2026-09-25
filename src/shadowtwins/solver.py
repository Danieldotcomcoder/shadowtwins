"""Exhaustive exact certification (``st-solver-1.0.0``).

Every permitted relocation set is enumerated exactly once: for ``r = 0..min(b, s, e)``, every
``r``-subset of originally-solid editable IDs paired with every ``r``-subset of originally-empty
editable IDs, both in ascending lexicographic ID order. That is

    sum_r C(s, r) * C(e, r)

candidates (16,526 for s = e = 10, b = 3). A candidate is legal when its three silhouettes equal
the original's and its solid cells stay face-connected; all other rules hold by construction.
The optimum is the maximum objective over legal candidates. Timed-out or partial searches are
never certified: this module has no time limit and no heuristics.
"""

from __future__ import annotations

import datetime as dt
import platform
import time
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from math import comb

from benchcore.hashing import content_hash

from . import grid
from .contracts import (
    CertificateCore,
    CertificateRun,
    ConstraintTotals,
    NoShadowAblation,
    RejectionCounts,
    ShadowTwinsCertificate,
    ShadowTwinsInstance,
    Witness,
)
from .engine import Compiled, compile_instance, entrance_labels, pair_changes
from .versions import (
    EVALUATOR_VERSION,
    GENERATOR_VERSION,
    PROTOCOL_VERSION,
    RULES_VERSION,
    SOLVER_VERSION,
)


def expected_candidate_count(s: int, e: int, b: int) -> int:
    return sum(comb(s, r) * comb(e, r) for r in range(min(b, s, e) + 1))


@dataclass
class Candidate:
    moves: int
    remove: tuple[int, ...]
    add: tuple[int, ...]
    final: int


def iter_candidates(c: Compiled):
    """All permitted relocation sets in canonical order (see module docstring)."""
    s_ids, e_ids = c.solid_ids, c.empty_ids
    for r in range(min(c.budget, len(s_ids), len(e_ids)) + 1):
        add_sets = [(a, grid.mask_of(c.editable[k] for k in a)) for a in combinations(e_ids, r)]
        for rm in combinations(s_ids, r):
            base = c.occ & ~grid.mask_of(c.editable[k] for k in rm)
            for ad, am in add_sets:
                yield r, rm, ad, base | am


@dataclass
class EnumerationResult:
    enumerated: int = 0
    legal: int = 0
    histogram: Counter[int] = field(default_factory=Counter)
    by_moves: dict[int, Counter[int]] = field(default_factory=dict)
    best: tuple[int, tuple[int, ...], tuple[int, ...]] | None = None
    best_v: int = -1
    worst: tuple[int, tuple[int, ...], tuple[int, ...]] | None = None
    worst_v: int = 1 << 30
    rej_silhouette: int = 0
    rej_solid: int = 0
    tot_sil_fail: int = 0
    tot_solid_fail: int = 0
    tot_both: int = 0
    ns_legal: int = 0
    ns_hist: Counter[int] = field(default_factory=Counter)
    ns_best: tuple[int, tuple[int, ...], tuple[int, ...]] | None = None
    ns_best_v: int = -1


def enumerate_instance(c: Compiled, with_ablation: bool = True) -> EnumerationResult:
    """Run the exhaustive enumeration. ``with_ablation`` also evaluates the no-shadow variant,
    which requires connectivity and objective for silhouette-failing candidates too."""
    res = EnumerationResult()
    kx, ky, kz = c.sil
    labels_a = c.labels
    ents = c.entrances
    px, py, pz = grid.project_x_key, grid.project_y_key, grid.project_z_key
    connected = grid.is_connected
    for r, rm, ad, final in iter_candidates(c):
        res.enumerated += 1
        sil_ok = px(final) == kx and py(final) == ky and pz(final) == kz
        if not sil_ok and not with_ablation:
            res.rej_silhouette += 1
            continue
        conn_ok = connected(final)
        if not sil_ok:
            res.tot_sil_fail += 1
            res.rej_silhouette += 1
        if not conn_ok:
            res.tot_solid_fail += 1
            if sil_ok:
                res.rej_solid += 1
            else:
                res.tot_both += 1
            continue
        opened, closed = pair_changes(labels_a, entrance_labels(final, ents))
        v = opened + closed
        if with_ablation:
            res.ns_legal += 1
            res.ns_hist[v] += 1
            if v > res.ns_best_v:
                res.ns_best_v, res.ns_best = v, (r, rm, ad)
        if not sil_ok:
            continue
        res.legal += 1
        res.histogram[v] += 1
        res.by_moves.setdefault(r, Counter())[v] += 1
        if v > res.best_v:
            res.best_v, res.best = v, (r, rm, ad)
        if v < res.worst_v:
            res.worst_v, res.worst = v, (r, rm, ad)
    return res


def _witness(w: tuple[int, tuple[int, ...], tuple[int, ...]] | None, v: int) -> Witness | None:
    if w is None:
        return None
    return Witness(remove=list(w[1]), add=list(w[2]), objective=v)


def certificate_versions(inst: ShadowTwinsInstance) -> dict[str, str]:
    return {
        "rules": RULES_VERSION,
        "solver": SOLVER_VERSION,
        "evaluator": EVALUATOR_VERSION,
        "protocol": PROTOCOL_VERSION,
        "generator": inst.meta.generator_version or GENERATOR_VERSION,
    }


def certify(inst: ShadowTwinsInstance) -> ShadowTwinsCertificate:
    t0 = time.perf_counter()
    c = compile_instance(inst)
    res = enumerate_instance(c, with_ablation=True)
    s, e = len(c.solid_ids), len(c.empty_ids)
    expected = expected_candidate_count(s, e, c.budget)
    if res.enumerated != expected:  # pragma: no cover - guards the enumerator itself
        raise RuntimeError(f"enumerated {res.enumerated} candidates, expected {expected}")
    best = _witness(res.best, res.best_v)
    worst = _witness(res.worst, res.worst_v)
    assert best is not None and worst is not None  # the no-op is always legal
    min_moves = min((r for r, h in res.by_moves.items() if h.get(res.best_v, 0) > 0), default=None)
    core = CertificateCore(
        instance_id=inst.instance_id,
        instance_hash=inst.content_hash,
        versions=certificate_versions(inst),
        budget=c.budget,
        solid_editable=s,
        empty_editable=e,
        expected_enumerated_count=expected,
        enumerated_count=res.enumerated,
        legal_count=res.legal,
        v_star=res.best_v,
        v_min=res.worst_v,
        optimal_count=res.histogram[res.best_v],
        min_moves_for_optimum=min_moves if res.best_v > 0 else 0,
        histogram={str(k): res.histogram[k] for k in sorted(res.histogram)},
        histogram_by_moves={
            str(r): {str(k): h[k] for k in sorted(h)} for r, h in sorted(res.by_moves.items())
        },
        best_witness=best,
        worst_witness=worst,
        rejections=RejectionCounts(silhouette=res.rej_silhouette, solid_disconnected=res.rej_solid),
        constraint_totals=ConstraintTotals(silhouette_fail=res.tot_sil_fail,
                                           solid_disconnected=res.tot_solid_fail,
                                           both=res.tot_both),
        no_shadow=NoShadowAblation(
            legal_count=res.ns_legal, v_star=res.ns_best_v,
            histogram={str(k): res.ns_hist[k] for k in sorted(res.ns_hist)},
            best_witness=_witness(res.ns_best, res.ns_best_v),
        ),
        admissible=res.best_v > 0,
        inadmissible_reason=None if res.best_v > 0 else "v_star = 0: no legal edit changes any pair",
    )
    runtime_ms = (time.perf_counter() - t0) * 1000
    return ShadowTwinsCertificate(
        core=core,
        core_hash=content_hash(core),
        run=CertificateRun(
            runtime_ms=round(runtime_ms, 3),
            created_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            python=platform.python_version(),
        ),
    )
