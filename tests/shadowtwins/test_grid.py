import random

from shadowtwins import grid
from stverify.core import shadows


def test_index_roundtrip_and_convention():
    assert grid.index(1, 0, 0) == 1
    assert grid.index(0, 1, 0) == 4
    assert grid.index(0, 0, 1) == 16
    for i in range(64):
        assert grid.index(*grid.coords(i)) == i


def test_neighbors_do_not_wrap():
    # (3,0,0) must not see (0,1,0); (0,3,0) must not see (0,0,1) via y overflow.
    n = grid.neighbors(1 << grid.index(3, 0, 0))
    assert not (n >> grid.index(0, 1, 0)) & 1
    assert {grid.coords(i) for i in grid.bits(n)} == {(2, 0, 0), (3, 1, 0), (3, 0, 1)}
    n = grid.neighbors(1 << grid.index(0, 3, 0))
    assert {grid.coords(i) for i in grid.bits(n)} == {(1, 3, 0), (0, 2, 0), (0, 3, 1)}
    n = grid.neighbors(1 << grid.index(1, 2, 3))
    assert len(list(grid.bits(n))) == 5  # top face cell has no +z neighbour
    for i in range(64):
        x, y, z = grid.coords(i)
        expected = sum(1 for d in (x, y, z) for v in (d - 1, d + 1) if 0 <= v < 4)
        assert grid.popcount(grid.neighbors(1 << i)) == expected


def test_connectivity_and_components():
    line = grid.mask_of(grid.index(x, 0, 0) for x in range(4))
    assert grid.is_connected(line)
    gap = line & ~(1 << grid.index(2, 0, 0))
    assert not grid.is_connected(gap)
    assert len(grid.components(gap)) == 2
    diag = (1 << grid.index(0, 0, 0)) | (1 << grid.index(1, 1, 0))
    assert not grid.is_connected(diag)  # no diagonal adjacency
    assert not grid.is_connected(0)


def test_silhouette_rows_orientation():
    m = 1 << grid.index(1, 2, 3)
    rows = grid.silhouette_rows(m)
    assert rows["x"][3][2] == 1 and sum(map(sum, rows["x"])) == 1  # rows[z][y]
    assert rows["y"][3][1] == 1 and sum(map(sum, rows["y"])) == 1  # rows[z][x]
    assert rows["z"][2][1] == 1 and sum(map(sum, rows["z"])) == 1  # rows[y][x]


def test_projection_keys_match_plain_loops():
    rng = random.Random(7)
    for _ in range(2000):
        a = rng.getrandbits(64) & rng.getrandbits(64)
        b = a ^ (1 << rng.randrange(64)) ^ (1 << rng.randrange(64))
        sa = shadows({grid.coords(i) for i in grid.bits(a)})
        sb = shadows({grid.coords(i) for i in grid.bits(b)})
        assert (grid.silhouette_keys(a) == grid.silhouette_keys(b)) == (sa == sb)
        rows = grid.silhouette_rows(a)
        assert {(u, v) for v in range(4) for u in range(4) if rows["x"][v][u]} == set(sa[0])
        assert {(u, v) for v in range(4) for u in range(4) if rows["y"][v][u]} == set(sa[1])
        assert {(u, v) for v in range(4) for u in range(4) if rows["z"][v][u]} == set(sa[2])


def test_occupancy_string_roundtrip():
    rng = random.Random(3)
    for _ in range(100):
        m = rng.getrandbits(64)
        assert grid.occupancy_from_string(grid.occupancy_to_string(m)) == m
