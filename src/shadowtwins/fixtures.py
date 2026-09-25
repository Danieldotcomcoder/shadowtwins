"""Hand-checked formal fixtures (split = "fixture").

Each fixture documents its expected certificate values, derived by hand in
docs/FORMAL_RULES.md ("Worked fixtures") and asserted in tests. They are formal checks of the
mathematics, not benchmark content: they never enter practice or ranked packs.
"""

from __future__ import annotations

from . import grid
from .contracts import InstanceMeta, ShadowTwinsInstance

Cell = tuple[int, int, int]


def _block_minus(empty: list[Cell]) -> int:
    occ = grid.FULL
    for c in empty:
        occ &= ~(1 << grid.index(*c))
    return occ


BENT_TUNNEL: list[Cell] = [(0, 1, 1), (1, 1, 1), (2, 1, 1), (2, 2, 1), (2, 3, 1)]


def bent_tunnel_block() -> ShadowTwinsInstance:
    """Full block with an L-shaped tunnel A(0,1,1) -> (2,1,1) -> B(2,3,1) and a sealed
    entrance C(3,0,3). Budget 1; only closing the tunnel is possible.

    Expected: enumerated 4, legal 4, histogram {0:1, 1:3}, v* = 1, best remove [1] add [0].
    """
    return ShadowTwinsInstance.build(
        instance_id="fx-bent-tunnel-block",
        occupancy=_block_minus([*BENT_TUNNEL, (3, 0, 3)]),
        entrances=[(0, 1, 1), (2, 3, 1), (3, 0, 3)],
        editable=[(1, 1, 1), (1, 1, 2), (3, 0, 2), (3, 1, 3)],
        budget=1,
        meta=InstanceMeta(label="Bent tunnel in a block", split="fixture"),
    )


def bent_tunnel_shadow_gate() -> ShadowTwinsInstance:
    """Bent tunnel plus entrance C(3,2,2) behind a one-cube gate (3,2,1) and an isolated cavity
    (1,2,2). Cube (3,1,1) is the only solid on the x-ray through the tunnel's first row, so it may
    only leave if a cube lands on the same ray.

    Expected: enumerated 5, legal 4, histogram {0:1, 1:1, 2:2}, v* = 2, optimal_count 2,
    best remove [0] add [2]; rejections silhouette 1.
    """
    return ShadowTwinsInstance.build(
        instance_id="fx-shadow-gate",
        occupancy=_block_minus([*BENT_TUNNEL, (3, 2, 2), (1, 2, 2)]),
        entrances=[(0, 1, 1), (2, 3, 1), (3, 2, 2)],
        editable=[(3, 2, 1), (3, 1, 1), (1, 1, 1), (1, 2, 2)],
        budget=1,
        meta=InstanceMeta(label="Shadow gate", split="fixture"),
    )


def straight_tunnel_zero() -> ShadowTwinsInstance:
    """Straight tunnel along x at (y=1, z=1): its x-ray is empty, so filling any tunnel cell
    changes the x silhouette. Corner cube (3,3,3) hangs on (3,3,2).

    Expected: v* = 0 (inadmissible), legal 3, silhouette rejections 2, solid totals 1 (both 1);
    without the shadow rule v* would be 1.
    """
    tunnel = [(x, 1, 1) for x in range(4)]
    return ShadowTwinsInstance.build(
        instance_id="fx-straight-tunnel-zero",
        occupancy=_block_minus([*tunnel, (2, 3, 3), (3, 2, 3)]),
        entrances=[(0, 1, 1), (3, 1, 1)],
        editable=[(3, 3, 2), (1, 1, 1), (1, 1, 2), (3, 2, 3)],
        budget=1,
        meta=InstanceMeta(label="Shadow-protected straight tunnel", split="fixture"),
    )


def snake_ten_by_ten() -> ShadowTwinsInstance:
    """A winding tunnel network with 5 entrances, 10 solid and 10 empty editable cells, b = 3.
    Enumeration count must be 1 + 100 + 45^2 + 120^2 = 16,526. Values are cross-checked against
    the independent verifier rather than by hand."""
    empty: list[Cell] = [
        # lower snake: A(0,0,0) -> ... -> B(3,3,0)
        (0, 0, 0), (1, 0, 0), (1, 1, 0), (1, 2, 0), (2, 2, 0), (3, 2, 0), (3, 3, 0),
        # riser from (1,2,0) up to a middle gallery
        (1, 2, 1), (1, 2, 2), (2, 2, 2), (2, 1, 2), (3, 1, 2),
        # upper gallery ending at D(0,3,3) and E(3,0,3)
        (1, 2, 3), (0, 2, 3), (0, 3, 3), (3, 0, 3), (3, 0, 2),
        # isolated pockets
        (2, 0, 1), (0, 3, 1),
    ]
    solid_editable: list[Cell] = [
        (1, 1, 1), (2, 2, 1), (1, 3, 2), (2, 1, 1), (0, 2, 2),
        (2, 0, 2), (3, 1, 1), (1, 1, 2), (2, 3, 3), (1, 0, 1),
    ]
    empty_editable: list[Cell] = [
        (1, 1, 0), (2, 2, 0), (1, 2, 1), (2, 2, 2), (2, 1, 2),
        (1, 2, 3), (0, 2, 3), (2, 0, 1), (0, 3, 1), (3, 0, 2),
    ]
    return ShadowTwinsInstance.build(
        instance_id="fx-snake-10x10",
        occupancy=_block_minus(empty),
        entrances=[(0, 0, 0), (3, 3, 0), (3, 1, 2), (0, 3, 3), (3, 0, 3)],
        editable=solid_editable + empty_editable,
        budget=3,
        meta=InstanceMeta(label="Snake network, s = e = 10, b = 3", split="fixture"),
    )


def all_fixtures() -> list[ShadowTwinsInstance]:
    return [bent_tunnel_block(), bent_tunnel_shadow_gate(), straight_tunnel_zero(), snake_ten_by_ten()]
