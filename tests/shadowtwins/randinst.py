"""Small random instances for property tests (not the P2 generator)."""

from __future__ import annotations

import random

from shadowtwins import grid
from shadowtwins.contracts import InstanceMeta, ShadowTwinsInstance


def random_blob(rng: random.Random, size: int) -> int:
    """A random face-connected set of ``size`` cells grown from a random seed cell."""
    occ = 1 << rng.randrange(64)
    while grid.popcount(occ) < size:
        frontier = list(grid.bits(grid.neighbors(occ) & ~occ))
        occ |= 1 << rng.choice(frontier)
    return occ


def random_instance(rng: random.Random, n_solid: int = 5, n_empty: int = 5, budget: int = 2,
                    fill: int | None = None) -> ShadowTwinsInstance | None:
    occ = random_blob(rng, fill if fill is not None else rng.randrange(28, 52))
    empty_boundary = [i for i in range(64) if not (occ >> i) & 1 and grid.is_boundary(i)]
    if len(empty_boundary) < 3:
        return None
    ents = rng.sample(empty_boundary, rng.randrange(2, min(6, len(empty_boundary)) + 1))
    solids = [i for i in range(64) if (occ >> i) & 1]
    empties = [i for i in range(64) if not (occ >> i) & 1 and i not in ents]
    if len(solids) < n_solid or len(empties) < n_empty:
        return None
    editable = rng.sample(solids, n_solid) + rng.sample(empties, n_empty)
    rng.shuffle(editable)
    return ShadowTwinsInstance.build(
        instance_id=f"rand-{rng.randrange(10**9)}",
        occupancy=occ,
        entrances=[grid.coords(i) for i in ents],
        editable=[grid.coords(i) for i in editable],
        budget=budget,
        meta=InstanceMeta(split="fixture"),
    )


def random_instances(seed: int, count: int, **kw) -> list[ShadowTwinsInstance]:
    rng = random.Random(seed)
    out: list[ShadowTwinsInstance] = []
    while len(out) < count:
        inst = random_instance(rng, **kw)
        if inst is not None:
            out.append(inst)
    return out
