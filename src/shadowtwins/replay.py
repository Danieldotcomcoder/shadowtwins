"""Deterministic replay documents for the inspection views (``st-replay-1.0.0``).

Everything here is derived from authoritative engine results; the browser only draws it. Paths
are breadth-first shortest paths through empty cells with the fixed neighbour order
``-x, +x, -y, +y, -z, +z``, so the same inputs always yield the same route.
"""

from __future__ import annotations

from collections import deque

from . import grid
from .contracts import (
    Component,
    Edit,
    EditableCellInfo,
    EntranceInfo,
    GridState,
    OutcomeView,
    PairChange,
    PairStatus,
    PathTrace,
    ShadowTwinsCertificate,
    ShadowTwinsEvaluation,
    ShadowTwinsInstance,
    ShadowTwinsReplay,
    Silhouettes,
)
from .engine import Compiled, compile_instance, entrance_labels
from .evaluate import evaluate_edit
from .versions import EVALUATOR_VERSION, REPLAY_VERSION

_STEPS = ((-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1))
LABELS = "ABCDEFGH"


def shortest_path(empty: int, start: int, goal: int) -> list[int] | None:
    if not ((empty >> start) & 1 and (empty >> goal) & 1):
        return None
    prev: dict[int, int] = {start: start}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        if cur == goal:
            path = [cur]
            while cur != start:
                cur = prev[cur]
                path.append(cur)
            return path[::-1]
        x, y, z = grid.coords(cur)
        for dx, dy, dz in _STEPS:
            nx, ny, nz = x + dx, y + dy, z + dz
            if 0 <= nx < grid.N and 0 <= ny < grid.N and 0 <= nz < grid.N:
                nxt = grid.index(nx, ny, nz)
                if nxt not in prev and (empty >> nxt) & 1:
                    prev[nxt] = cur
                    queue.append(nxt)
    return None


def _coords_list(m: int) -> list[tuple[int, int, int]]:
    return [grid.coords(i) for i in grid.bits(m)]


def grid_state(occ: int, entrances: tuple[int, ...]) -> GridState:
    empty = ~occ & grid.FULL
    ent_comp: list[int] = [-1] * len(entrances)
    comps: list[Component] = []
    covered = 0
    for k, e in enumerate(entrances):
        if ent_comp[k] != -1 or not (empty >> e) & 1:
            continue
        comp = grid.flood(1 << e, empty)
        cid = len(comps)
        members = [j for j, ej in enumerate(entrances) if (comp >> ej) & 1]
        for j in members:
            ent_comp[j] = cid
        comps.append(Component(id=cid, cells=_coords_list(comp), entrances=members))
        covered |= comp
    solid = [Component(id=i, cells=_coords_list(m)) for i, m in enumerate(grid.components(occ))]
    paths: list[PathTrace] = []
    for i in range(len(entrances)):
        for j in range(i + 1, len(entrances)):
            if ent_comp[i] != -1 and ent_comp[i] == ent_comp[j]:
                p = shortest_path(empty, entrances[i], entrances[j])
                assert p is not None
                paths.append(PathTrace(i=i, j=j, cells=[grid.coords(c) for c in p]))
    sil = grid.silhouette_rows(occ)
    return GridState(
        occupancy=grid.occupancy_to_string(occ),
        silhouettes=Silhouettes(**sil),
        empty_components=comps,
        other_empty_cells=_coords_list(empty & ~covered),
        solid_components=solid,
        entrance_component=ent_comp,
        paths=paths,
    )


def _mismatch(a: int, b: int) -> Silhouettes:
    ra, rb = grid.silhouette_rows(a), grid.silhouette_rows(b)
    return Silhouettes(**{
        ax: [[int(ra[ax][v][u] != rb[ax][v][u]) for u in range(grid.N)] for v in range(grid.N)]
        for ax in ("x", "y", "z")
    })


def _pairs(c: Compiled, final: int) -> list[PairStatus]:
    la, lb = c.labels, entrance_labels(final, c.entrances)
    out: list[PairStatus] = []
    for i in range(len(la)):
        for j in range(i + 1, len(la)):
            o, f = la[i] == la[j], lb[i] == lb[j]
            change = PairChange.OPENED if f and not o else PairChange.CLOSED if o and not f else PairChange.UNCHANGED
            out.append(PairStatus(i=i, j=j, original=o, final=f, change=change))
    return out


def outcome_view(
    label: str, c: Compiled, evaluation: ShadowTwinsEvaluation
) -> OutcomeView:
    final_occ = (grid.occupancy_from_string(evaluation.final_occupancy)
                 if evaluation.final_occupancy is not None else None)
    removed: list[tuple[int, int, int]] = []
    added: list[tuple[int, int, int]] = []
    if final_occ is not None:
        removed = _coords_list(c.occ & ~final_occ)
        added = _coords_list(final_occ & ~c.occ)
    return OutcomeView(
        label=label,  # type: ignore[arg-type]
        edit=evaluation.edit,
        valid=evaluation.valid,
        category=evaluation.category,
        checks=evaluation.checks,
        final=grid_state(final_occ, c.entrances) if final_occ is not None else None,
        removed=removed,
        added=added,
        silhouette_mismatch=_mismatch(c.occ, final_occ) if final_occ is not None else None,
        # Pair changes are only reported for legal results: an invalid object never
        # "opens" or "closes" routes in the scored sense.
        pairs=_pairs(c, final_occ) if final_occ is not None and evaluation.valid else [],
        raw_objective=evaluation.raw_objective,
        v_star=evaluation.v_star,
        score=evaluation.score,
        opened=evaluation.opened,
        closed=evaluation.closed,
        move_count=evaluation.move_count,
    )


def build_replay(
    inst: ShadowTwinsInstance,
    cert: ShadowTwinsCertificate,
    model_evaluation: ShadowTwinsEvaluation | None = None,
    model_label: str = "model",
) -> ShadowTwinsReplay:
    if cert.core.instance_hash != inst.content_hash:
        raise ValueError("certificate does not belong to this instance")
    c = compile_instance(inst)
    v_star = cert.core.v_star
    w = cert.core.best_witness
    optimal_eval = evaluate_edit(inst, v_star, Edit(remove=w.remove, add=w.add), c)
    if not optimal_eval.valid or optimal_eval.raw_objective != v_star:
        raise RuntimeError("certified optimum witness does not re-evaluate to v_star")
    if model_evaluation is not None and model_evaluation.instance_hash != inst.content_hash:
        raise ValueError("evaluation does not belong to this instance")
    return ShadowTwinsReplay(
        replay_version=REPLAY_VERSION,
        evaluator_version=EVALUATOR_VERSION,
        instance_id=inst.instance_id,
        instance_hash=inst.content_hash,
        certificate_hash=cert.core_hash,
        budget=c.budget,
        editable=[EditableCellInfo(id=k, cell=grid.coords(cell), originally_solid=bool((c.occ >> cell) & 1))
                  for k, cell in enumerate(c.editable)],
        entrances=[EntranceInfo(index=k, label=LABELS[k], cell=grid.coords(e))
                   for k, e in enumerate(c.entrances)],
        original=grid_state(c.occ, c.entrances),
        optimal=outcome_view("optimal", c, optimal_eval),
        model=outcome_view(model_label, c, model_evaluation) if model_evaluation else None,
    )
