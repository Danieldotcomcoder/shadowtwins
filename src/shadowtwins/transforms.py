"""The 48 symmetries of the cube acting on instances (axis permutations x reflections).

Used for (a) invariance tests: certified extrema must not change under a whole-instance symmetry,
and (b) duplicate detection: two instances are symmetry-equivalent when some symmetry maps one's
occupancy, entrance set, editable set and budget onto the other's. Coordinates are anchored in the
task itself — a model may not rotate the object — so symmetries are only an analysis tool.
"""

from __future__ import annotations

from itertools import permutations, product

from benchcore.hashing import canonical_json

from . import grid
from .contracts import InstanceMeta, ShadowTwinsInstance

Symmetry = tuple[tuple[int, int, int], tuple[bool, bool, bool]]

SYMMETRIES: list[Symmetry] = [
    (perm, flips)  # type: ignore[misc]
    for perm in permutations(range(3))
    for flips in product((False, True), repeat=3)
]
IDENTITY: Symmetry = ((0, 1, 2), (False, False, False))


def apply_to_coord(sym: Symmetry, cell: tuple[int, int, int]) -> tuple[int, int, int]:
    perm, flips = sym
    out = [cell[perm[k]] for k in range(3)]
    return tuple(grid.N - 1 - out[k] if flips[k] else out[k] for k in range(3))  # type: ignore[return-value]


def apply_to_mask(sym: Symmetry, m: int) -> int:
    out = 0
    for i in grid.bits(m):
        out |= 1 << grid.index(*apply_to_coord(sym, grid.coords(i)))
    return out


def transform_instance(inst: ShadowTwinsInstance, sym: Symmetry, suffix: str = "t") -> ShadowTwinsInstance:
    """Apply ``sym`` to geometry while keeping entrance and editable ID order unchanged, so an
    answer's IDs keep their meaning."""
    return ShadowTwinsInstance.build(
        instance_id=f"{inst.instance_id}-{suffix}",
        occupancy=apply_to_mask(sym, inst.occupancy_mask),
        entrances=[apply_to_coord(sym, tuple(c)) for c in inst.core.entrances],  # type: ignore[arg-type]
        editable=[apply_to_coord(sym, tuple(c)) for c in inst.core.editable],  # type: ignore[arg-type]
        budget=inst.core.budget,
        meta=InstanceMeta(label=inst.meta.label, notes=f"symmetry {sym} of {inst.instance_id}"),
    )


def canonical_key(occ: int, entrances: list[int], editable: list[int], budget: int) -> str:
    """Symmetry-invariant key: the minimum serialization over all 48 images, with entrance and
    editable lists treated as sets (ID order is presentation, not geometry)."""
    best: str | None = None
    for sym in SYMMETRIES:
        o = apply_to_mask(sym, occ)
        ents = sorted(grid.index(*apply_to_coord(sym, grid.coords(i))) for i in entrances)
        eds = sorted(grid.index(*apply_to_coord(sym, grid.coords(i))) for i in editable)
        key = canonical_json([grid.occupancy_to_string(o), ents, eds, budget])
        if best is None or key < best:
            best = key
    assert best is not None
    return best


def instance_canonical_key(inst: ShadowTwinsInstance) -> str:
    return canonical_key(inst.occupancy_mask, inst.entrance_indices, inst.editable_indices,
                         inst.core.budget)
