"""Optimized exact engine: compiled instances, legality and the entrance-pair objective.

This is the authoritative implementation used for certification and scoring. It is deliberately
independent of ``stverify`` (the simple verifier), which re-derives the same facts with plain loops
and graph traversal; the two are compared in tests and by ``shadowtwins-verify``.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import grid
from .contracts import ShadowTwinsInstance
from .versions import MAX_BUDGET, MAX_ENTRANCES, MIN_BUDGET, MIN_ENTRANCES


@dataclass(frozen=True, slots=True)
class Compiled:
    occ: int
    entrances: tuple[int, ...]  # cell indices, in entrance order
    editable: tuple[int, ...]  # cell indices, position = editable ID
    budget: int
    solid_ids: tuple[int, ...]  # editable IDs whose cell is solid in the original
    empty_ids: tuple[int, ...]  # editable IDs whose cell is empty in the original
    editable_mask: int
    entrance_mask: int
    sil: tuple[int, int, int]
    labels: tuple[int, ...]  # entrance partition labels in the original

    @property
    def pair_count(self) -> int:
        k = len(self.entrances)
        return k * (k - 1) // 2


def structural_problems(inst: ShadowTwinsInstance) -> list[str]:
    """Structural instance checks (certification is separate)."""
    problems: list[str] = []
    occ = inst.occupancy_mask
    ents = inst.entrance_indices
    eds = inst.editable_indices
    if not (MIN_BUDGET <= inst.core.budget <= MAX_BUDGET):
        problems.append(f"budget {inst.core.budget} outside {MIN_BUDGET}..{MAX_BUDGET}")
    if not (MIN_ENTRANCES <= len(ents) <= MAX_ENTRANCES):
        problems.append(f"entrance count {len(ents)} outside {MIN_ENTRANCES}..{MAX_ENTRANCES}")
    if len(set(ents)) != len(ents):
        problems.append("entrances are not distinct")
    if len(set(eds)) != len(eds):
        problems.append("editable cells are not distinct")
    for k, e in enumerate(ents):
        if (occ >> e) & 1:
            problems.append(f"entrance {k} {grid.coords(e)} is solid")
        if not grid.is_boundary(e):
            problems.append(f"entrance {k} {grid.coords(e)} is not a boundary cell")
    overlap = set(ents) & set(eds)
    if overlap:
        problems.append(f"entrances listed as editable: {sorted(grid.coords(i) for i in overlap)}")
    if occ == 0:
        problems.append("original object has no solid cells")
    elif not grid.is_connected(occ):
        problems.append("original solid cells are not one face-connected component")
    return problems


def compile_instance(inst: ShadowTwinsInstance) -> Compiled:
    problems = structural_problems(inst)
    if problems:
        raise ValueError("invalid instance: " + "; ".join(problems))
    occ = inst.occupancy_mask
    ents = tuple(inst.entrance_indices)
    eds = tuple(inst.editable_indices)
    solid_ids = tuple(k for k, c in enumerate(eds) if (occ >> c) & 1)
    empty_ids = tuple(k for k, c in enumerate(eds) if not (occ >> c) & 1)
    return Compiled(
        occ=occ,
        entrances=ents,
        editable=eds,
        budget=inst.core.budget,
        solid_ids=solid_ids,
        empty_ids=empty_ids,
        editable_mask=grid.mask_of(eds),
        entrance_mask=grid.mask_of(ents),
        sil=grid.silhouette_keys(occ),
        labels=entrance_labels(occ, ents),
    )


def entrance_labels(occ: int, entrances: tuple[int, ...]) -> tuple[int, ...]:
    """Partition labels of entrances by empty-cell component (label = first entrance's order)."""
    empty = ~occ & grid.FULL
    labels = [-1] * len(entrances)
    nxt = 0
    for a, ea in enumerate(entrances):
        if labels[a] != -1:
            continue
        if not (empty >> ea) & 1:
            # A solid entrance cell is its own isolated label (only reachable via invalid grids).
            labels[a] = nxt
            nxt += 1
            continue
        comp = grid.flood(1 << ea, empty)
        for b in range(a, len(entrances)):
            if labels[b] == -1 and (comp >> entrances[b]) & 1:
                labels[b] = nxt
        nxt += 1
    return tuple(labels)


def pair_changes(la: tuple[int, ...], lb: tuple[int, ...]) -> tuple[int, int]:
    """(opened, closed) over unordered entrance pairs between two labelings."""
    opened = closed = 0
    k = len(la)
    for i in range(k):
        for j in range(i + 1, k):
            ca = la[i] == la[j]
            cb = lb[i] == lb[j]
            if cb and not ca:
                opened += 1
            elif ca and not cb:
                closed += 1
    return opened, closed


def objective(c: Compiled, final_occ: int) -> tuple[int, int, int]:
    """(v, opened, closed) for a final occupancy."""
    opened, closed = pair_changes(c.labels, entrance_labels(final_occ, c.entrances))
    return opened + closed, opened, closed


def apply_ids(c: Compiled, remove: list[int] | tuple[int, ...], add: list[int] | tuple[int, ...]) -> int:
    """Final occupancy for in-range editable IDs, applied simultaneously as requested."""
    occ = c.occ
    for k in remove:
        occ &= ~(1 << c.editable[k])
    for k in add:
        occ |= 1 << c.editable[k]
    return occ


def is_legal_final(c: Compiled, final_occ: int) -> bool:
    """Silhouettes and solid connectivity (edit-shape rules are checked by the evaluator)."""
    return grid.silhouette_keys(final_occ) == c.sil and grid.is_connected(final_occ)
