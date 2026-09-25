"""Seeded instance generator (``st-gen-1.0.0``). Owned by P2.

Each candidate is a pure function of ``(seed, params)``:

1. start from the full 4x4x4 block;
2. carve 3-5 tunnels as direction-persistent random walks, some starting on the boundary (mouths)
   and some branching off earlier tunnels;
3. carve 1-3 isolated interior cavities;
4. erode random exposed solid cells (never disconnecting the solid) down to a target fill, which
   thins silhouette rays so the shadow rule constrains edits;
5. mark 5-8 empty boundary cells as entrances, preferring tunnel mouths;
6. choose editable cells among solid "wall" cells touching empty space and empty cells touching
   solid, then order IDs as solid cells first, then empty cells, each by flat index.

Generation does not guarantee a useful puzzle. Candidates are certified exhaustively and kept only
if they satisfy the frozen admission policy (``shadowtwins.policy``).
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass

from . import grid
from .contracts import InstanceMeta, ShadowTwinsInstance
from .versions import GENERATOR_VERSION

_DIRS = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))


@dataclass(frozen=True)
class GeneratorParams:
    budget: int = 2
    entrances: tuple[int, int] = (5, 8)
    solid_editable: tuple[int, int] = (6, 10)
    empty_editable: tuple[int, int] = (6, 10)
    fill: tuple[int, int] = (36, 46)
    tunnels: tuple[int, int] = (3, 5)
    tunnel_length: tuple[int, int] = (3, 8)
    cavities: tuple[int, int] = (1, 3)
    split: str = "development"
    id_prefix: str = "st"

    def as_dict(self) -> dict:
        return asdict(self)


def _walk(rng: random.Random, occ: int, start: int, length: int) -> int:
    """Carve a direction-persistent random walk; returns the new occupancy."""
    cur = start
    occ &= ~(1 << cur)
    d = rng.choice(_DIRS)
    for _ in range(length):
        if rng.random() > 0.55:
            d = rng.choice(_DIRS)
        x, y, z = grid.coords(cur)
        nx, ny, nz = x + d[0], y + d[1], z + d[2]
        if not (0 <= nx < 4 and 0 <= ny < 4 and 0 <= nz < 4):
            d = rng.choice(_DIRS)
            continue
        cur = grid.index(nx, ny, nz)
        occ &= ~(1 << cur)
    return occ


def _carve_tunnels(rng: random.Random, p: GeneratorParams, occ: int) -> tuple[int, list[int]]:
    mouths: list[int] = []
    boundary = [i for i in range(64) if grid.is_boundary(i)]
    for t in range(rng.randint(*p.tunnels)):
        carved = [i for i in range(64) if not (occ >> i) & 1]
        if t > 0 and carved and rng.random() < 0.4:
            start = rng.choice(carved)
        else:
            start = rng.choice(boundary)
            mouths.append(start)
        occ = _walk(rng, occ, start, rng.randint(*p.tunnel_length))
    return occ, mouths


def _carve_cavities(rng: random.Random, p: GeneratorParams, occ: int) -> int:
    for _ in range(rng.randint(*p.cavities)):
        empty = ~occ & grid.FULL
        candidates = [i for i in grid.bits(occ & ~grid.BOUNDARY)
                      if not grid.neighbors(1 << i) & empty]
        if not candidates:
            break
        occ &= ~(1 << rng.choice(candidates))
    return occ


def _erode(rng: random.Random, occ: int, target: int) -> int:
    """Remove exposed solid cells while the solid stays one piece."""
    attempts = 0
    while grid.popcount(occ) > target and attempts < 400:
        attempts += 1
        empty = ~occ & grid.FULL
        exposed = [i for i in grid.bits(occ)
                   if grid.is_boundary(i) or grid.neighbors(1 << i) & empty]
        cell = rng.choice(exposed)
        trial = occ & ~(1 << cell)
        if grid.is_connected(trial):
            occ = trial
    return occ


def generate_candidate(seed: int, params: GeneratorParams | None = None) -> ShadowTwinsInstance | None:
    """One candidate for ``seed``, or ``None`` when the draw cannot form a structurally valid
    instance (e.g. too few empty boundary cells)."""
    p = params or GeneratorParams()
    rng = random.Random(f"{GENERATOR_VERSION}:{seed}:{p.budget}")
    occ, mouths = _carve_tunnels(rng, p, grid.FULL)
    occ = _carve_cavities(rng, p, occ)
    if not grid.is_connected(occ):
        return None
    occ = _erode(rng, occ, rng.randint(*p.fill))
    if not grid.is_connected(occ):
        return None

    empty = ~occ & grid.FULL
    boundary_empty = [i for i in grid.bits(empty & grid.BOUNDARY)]
    n_ent = rng.randint(*p.entrances)
    if len(boundary_empty) < n_ent:
        return None
    preferred = sorted({i for i in mouths if (empty >> i) & 1})
    rng.shuffle(preferred)
    others = [i for i in boundary_empty if i not in preferred]
    rng.shuffle(others)
    entrances = sorted((preferred + others)[:n_ent])
    ent_mask = grid.mask_of(entrances)

    walls = [i for i in grid.bits(occ) if grid.neighbors(1 << i) & empty & ~ent_mask
             or grid.neighbors(1 << i) & ent_mask]
    holes = [i for i in grid.bits(empty & ~ent_mask) if grid.neighbors(1 << i) & occ]
    n_s = rng.randint(*p.solid_editable)
    n_e = rng.randint(*p.empty_editable)
    if len(walls) < n_s or len(holes) < n_e:
        return None
    solid_ed = sorted(rng.sample(walls, n_s))
    empty_ed = sorted(rng.sample(holes, n_e))

    return ShadowTwinsInstance.build(
        instance_id=f"{p.id_prefix}-b{p.budget}-{seed}",
        occupancy=occ,
        entrances=[grid.coords(i) for i in entrances],
        editable=[grid.coords(i) for i in solid_ed + empty_ed],
        budget=p.budget,
        meta=InstanceMeta(split=p.split, generator_version=GENERATOR_VERSION, seed=seed),  # type: ignore[arg-type]
    )
