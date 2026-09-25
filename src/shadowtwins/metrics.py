"""Per-instance measurements used for admission, tiers and research reports (P2).

All values derive from the exhaustive certificate and deterministic baselines; nothing here
involves a model.

Definitions:

* ``legal_density`` = legal / enumerated candidates.
* ``optimum_density`` = optimal / legal candidates (probability a uniform legal edit is optimal).
* ``shadow_rejection_rate`` = share of *otherwise permitted* candidates (solid stays connected;
  counts, budget and immutables hold by construction) that fail only because of the silhouette
  rule: ``1 - legal / no_shadow.legal``.
* ``shadow_traps`` = candidates that would reach at least ``v*`` without the silhouette rule but
  are illegal with it. At least one trap means shadow preservation actively removes an otherwise
  attractive choice.
* ``shadow_binding`` = the no-shadow optimum exceeds ``v*``.
* ``partial_levels`` = distinct objective values strictly between 0 and ``v*`` among legal edits.
"""

from __future__ import annotations

from typing import Any

from .baselines import LOCAL_SEARCH_BUDGET, local_search, random_legal_expectation
from .contracts import ShadowTwinsCertificate, ShadowTwinsInstance
from .engine import compile_instance
from .prompt import render_prompt


def instance_metrics(
    inst: ShadowTwinsInstance, cert: ShadowTwinsCertificate, with_tokens: bool = True
) -> dict[str, Any]:
    core = cert.core
    v_star = core.v_star
    levels = sorted(int(v) for v in core.histogram)
    ns = core.no_shadow
    ns_at_least = sum(n for v, n in ns.histogram.items() if int(v) >= v_star) if v_star else 0
    traps = ns_at_least - core.optimal_count if v_star else 0
    c = compile_instance(inst)
    ls = local_search(c, LOCAL_SEARCH_BUDGET)
    out: dict[str, Any] = {
        "instance_id": inst.instance_id,
        "budget": core.budget,
        "entrances": len(inst.core.entrances),
        "pairs": len(inst.core.entrances) * (len(inst.core.entrances) - 1) // 2,
        "solid_cells": inst.core.occupancy.count("1"),
        "solid_editable": core.solid_editable,
        "empty_editable": core.empty_editable,
        "enumerated": core.enumerated_count,
        "legal": core.legal_count,
        "v_star": v_star,
        "levels": levels,
        "partial_levels": [v for v in levels if 0 < v < v_star],
        "optimal_count": core.optimal_count,
        "min_moves_for_optimum": core.min_moves_for_optimum,
        "legal_density": core.legal_count / core.enumerated_count,
        "optimum_density": core.optimal_count / core.legal_count,
        "shadow_rejection_rate": 1 - core.legal_count / ns.legal_count if ns.legal_count else 0.0,
        "shadow_traps": traps,
        "shadow_binding": ns.v_star > v_star,
        "no_shadow_v_star": ns.v_star,
        "local_search_objective": ls.objective,
        "local_search_score": 100.0 * ls.objective / v_star if v_star else 0.0,
        "local_search_evaluations": ls.evaluations,
        "local_search_budget_exhausted": ls.stopped_by_budget,
        "certify_ms": cert.run.runtime_ms,
        **random_legal_expectation(cert),
    }
    if with_tokens:
        from .tokens import count_messages

        report = count_messages(render_prompt(inst).messages)
        out["tokens_max"] = report["max"]
        out["tokens"] = report["counts"]
    return out
