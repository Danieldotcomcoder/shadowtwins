"""Coordinate convention and bitboard primitives for the 4x4x4 Shadow Twins grid.

Coordinate convention (frozen for protocol v1, see docs/FORMAL_RULES.md):

* A cell is ``(x, y, z)`` with each coordinate in ``0..3``.
* ``x`` is the column: it increases left to right within a printed row.
* ``y`` is the row: it increases down the printed rows of a layer (``y=0`` is printed first).
* ``z`` is the layer: it increases upward (``z=0`` is the bottom layer).
* The flat cell index is ``i = x + 4*y + 16*z``. An occupancy is a 64-bit integer whose bit ``i``
  is 1 when cell ``i`` is solid.

Everything in this module is exact integer arithmetic. The optimized engine uses these bitboard
helpers; the independent verifier (``stverify``) deliberately does not import them.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

N = 4
NCELLS = N * N * N
FULL = (1 << NCELLS) - 1

Coord = tuple[int, int, int]


def index(x: int, y: int, z: int) -> int:
    """Flat index of cell ``(x, y, z)``."""
    if not (0 <= x < N and 0 <= y < N and 0 <= z < N):
        raise ValueError(f"cell out of range: {(x, y, z)}")
    return x + N * y + N * N * z


def coords(i: int) -> Coord:
    """Inverse of :func:`index`."""
    if not 0 <= i < NCELLS:
        raise ValueError(f"index out of range: {i}")
    return (i % N, (i // N) % N, i // (N * N))


def is_boundary(i: int) -> bool:
    """True when the cell lies on the outer surface of the grid."""
    return any(c in (0, N - 1) for c in coords(i))


def bit(i: int) -> int:
    return 1 << i


def mask_of(indices: Iterable[int]) -> int:
    m = 0
    for i in indices:
        m |= 1 << i
    return m


def bits(m: int) -> Iterator[int]:
    """Indices of set bits, ascending."""
    while m:
        low = m & -m
        yield low.bit_length() - 1
        m ^= low


def popcount(m: int) -> int:
    return m.bit_count()


def _plane_mask(axis: int, value: int) -> int:
    return mask_of(i for i in range(NCELLS) if coords(i)[axis] == value)


X0 = _plane_mask(0, 0)
X3 = _plane_mask(0, N - 1)
Y0 = _plane_mask(1, 0)
Y3 = _plane_mask(1, N - 1)
Z0 = _plane_mask(2, 0)
Z3 = _plane_mask(2, N - 1)
BOUNDARY = X0 | X3 | Y0 | Y3 | Z0 | Z3

# Canonical positions that hold each projection pixel after OR-folding (see project_*).
_PX_KEEP = X0  # pixel (y, z) of the view along x lives at bit index(0, y, z)
_PY_KEEP = Y0  # pixel (x, z) of the view along y lives at bit index(x, 0, z)
_PZ_KEEP = Z0  # pixel (x, y) of the view along z lives at bit index(x, y, 0)


def neighbors(m: int) -> int:
    """Union of face-neighbours of every cell in ``m`` (inside the grid, no wrap-around)."""
    return (
        ((m << 1) & ~X0)
        | ((m >> 1) & ~X3)
        | ((m << N) & ~Y0)
        | ((m >> N) & ~Y3)
        | (m << (N * N))
        | (m >> (N * N))
    ) & FULL


def flood(seed: int, allowed: int) -> int:
    """Face-connected closure of ``seed`` within ``allowed``."""
    comp = seed & allowed
    while True:
        grown = (comp | neighbors(comp)) & allowed
        if grown == comp:
            return comp
        comp = grown


def is_connected(m: int) -> bool:
    """True when ``m`` is non-empty and forms one face-connected component."""
    if m == 0:
        return False
    return flood(m & -m, m) == m


def components(m: int) -> list[int]:
    """Face-connected components of ``m``, ordered by their lowest cell index."""
    out: list[int] = []
    rest = m
    while rest:
        comp = flood(rest & -rest, rest)
        out.append(comp)
        rest &= ~comp
    return out


# --- exact orthographic OR projections -------------------------------------------------------

def project_x_key(m: int) -> int:
    """View along x: pixel (y, z) is solid when any cell (x, y, z) is solid.

    Returned as a 64-bit key with the pixel stored at ``index(0, y, z)``; two occupancies have
    equal x-silhouettes exactly when their keys are equal.
    """
    return (m | (m >> 1) | (m >> 2) | (m >> 3)) & _PX_KEEP


def project_y_key(m: int) -> int:
    """View along y: pixel (x, z) at ``index(x, 0, z)``."""
    return (m | (m >> N) | (m >> (2 * N)) | (m >> (3 * N))) & _PY_KEEP


def project_z_key(m: int) -> int:
    """View along z: pixel (x, y) at ``index(x, y, 0)``."""
    s = N * N
    return (m | (m >> s) | (m >> (2 * s)) | (m >> (3 * s))) & _PZ_KEEP


def silhouette_keys(m: int) -> tuple[int, int, int]:
    return (project_x_key(m), project_y_key(m), project_z_key(m))


def silhouette_rows(m: int) -> dict[str, list[list[int]]]:
    """The three masks as ``rows[v][u]`` 0/1 arrays.

    * ``x``: u = y, v = z
    * ``y``: u = x, v = z
    * ``z``: u = x, v = y
    """
    kx, ky, kz = silhouette_keys(m)
    return {
        "x": [[(kx >> index(0, u, v)) & 1 for u in range(N)] for v in range(N)],
        "y": [[(ky >> index(u, 0, v)) & 1 for u in range(N)] for v in range(N)],
        "z": [[(kz >> index(u, v, 0)) & 1 for u in range(N)] for v in range(N)],
    }


# --- serialization -----------------------------------------------------------------------------

def occupancy_to_string(m: int) -> str:
    """64 characters of '0'/'1'; character ``i`` is cell index ``i``."""
    return "".join("1" if (m >> i) & 1 else "0" for i in range(NCELLS))


def occupancy_from_string(s: str) -> int:
    if len(s) != NCELLS or any(c not in "01" for c in s):
        raise ValueError("occupancy must be exactly 64 characters of '0'/'1'")
    return sum(1 << i for i, c in enumerate(s) if c == "1")


def occupancy_layers(m: int) -> list[list[list[int]]]:
    """``layers[z][y][x]`` 0/1 nested lists."""
    return [
        [[(m >> index(x, y, z)) & 1 for x in range(N)] for y in range(N)] for z in range(N)
    ]
