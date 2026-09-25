import itertools
import random

from shadowtwins import fixtures, grid
from shadowtwins.contracts import Edit, PairChange
from shadowtwins.engine import compile_instance
from shadowtwins.evaluate import evaluate_edit, evaluate_text
from shadowtwins.replay import build_replay
from shadowtwins.solver import certify
from stverify.core import Puzzle, linked_pairs, shadows

from .randinst import random_instances


def _assert_state_consistent(state, entrances, puzzle_entrances):
    occ = grid.occupancy_from_string(state.occupancy)
    solid = {grid.coords(i) for i in grid.bits(occ)}
    # silhouettes equal the independent verifier's projections
    sx, sy, sz = shadows(solid)
    rows = state.silhouettes
    assert {(u, v) for v in range(4) for u in range(4) if rows.x[v][u]} == set(sx)
    assert {(u, v) for v in range(4) for u in range(4) if rows.y[v][u]} == set(sy)
    assert {(u, v) for v in range(4) for u in range(4) if rows.z[v][u]} == set(sz)
    # connected pairs from components equal the verifier's linked pairs
    comp = state.entrance_component
    from_components = {(i, j) for i in range(len(comp)) for j in range(i + 1, len(comp))
                       if comp[i] != -1 and comp[i] == comp[j]}
    assert from_components == linked_pairs(solid, puzzle_entrances)
    # every path is a real empty face-adjacent route between its endpoints
    assert {(p.i, p.j) for p in state.paths} == from_components
    for p in state.paths:
        cells = [tuple(c) for c in p.cells]
        assert cells[0] == tuple(entrances[p.i]) and cells[-1] == tuple(entrances[p.j])
        assert all(c not in solid for c in cells)
        for a, b in itertools.pairwise(cells):
            assert sum(abs(a[k] - b[k]) for k in range(3)) == 1
    # components partition matches solid components
    solid_cells = sorted(tuple(c) for comp in state.solid_components for c in comp.cells)
    assert solid_cells == sorted(solid)


def test_replays_match_independent_facts_on_random_instances():
    rng = random.Random(4)
    for inst in random_instances(31, 8, n_solid=5, n_empty=5, budget=2):
        cert = certify(inst)
        if not cert.core.admissible:
            continue
        c = compile_instance(inst)
        r = rng.randrange(0, 3)
        edit = Edit(remove=rng.sample(c.solid_ids, r), add=rng.sample(c.empty_ids, r))
        model = evaluate_edit(inst, cert.core.v_star, edit, c)
        rep = build_replay(inst, cert, model)
        p = Puzzle(inst.model_dump(mode="json"))
        _assert_state_consistent(rep.original, inst.core.entrances, p.entrances)
        _assert_state_consistent(rep.optimal.final, inst.core.entrances, p.entrances)
        assert rep.optimal.raw_objective == cert.core.v_star and rep.optimal.valid
        if model.final_occupancy is not None:
            _assert_state_consistent(rep.model.final, inst.core.entrances, p.entrances)


def test_shadow_gate_replay_pairs_and_edits():
    inst = fixtures.bent_tunnel_shadow_gate()
    cert = certify(inst)
    model = evaluate_text(inst, cert.core.v_star, '{"remove":[1],"add":[2]}')
    rep = build_replay(inst, cert, model)
    assert [e.label for e in rep.entrances] == ["A", "B", "C"]
    assert rep.model.removed == [(3, 1, 1)] and rep.model.added == [(1, 1, 1)]
    changes = {(p.i, p.j): p.change for p in rep.model.pairs}
    assert changes == {(0, 1): PairChange.CLOSED, (0, 2): PairChange.UNCHANGED, (1, 2): PairChange.UNCHANGED}
    assert all(v == 0 for rows in (rep.model.silhouette_mismatch.x, rep.model.silhouette_mismatch.y,
                                   rep.model.silhouette_mismatch.z) for row in rows for v in row)
    opt = {(p.i, p.j): p.change for p in rep.optimal.pairs}
    assert opt == {(0, 1): PairChange.CLOSED, (0, 2): PairChange.UNCHANGED, (1, 2): PairChange.OPENED}
    # original: A-B linked through the bent tunnel, 5 cells long
    assert [(p.i, p.j, len(p.cells)) for p in rep.original.paths] == [(0, 1, 5)]


def test_invalid_answer_replay_highlights_violation_without_pair_changes():
    inst = fixtures.bent_tunnel_shadow_gate()
    cert = certify(inst)
    model = evaluate_text(inst, cert.core.v_star, '{"remove":[1],"add":[3]}')
    rep = build_replay(inst, cert, model)
    assert not rep.model.valid and rep.model.pairs == []  # never animate as a valid result
    assert rep.model.silhouette_mismatch.x[1][1] == 1  # pixel (y=1, z=1) -> rows[z][y]
    assert sum(v for row in rep.model.silhouette_mismatch.x for v in row) == 1


def test_unparseable_answer_has_no_final_object():
    inst = fixtures.bent_tunnel_shadow_gate()
    cert = certify(inst)
    rep = build_replay(inst, cert, evaluate_text(inst, cert.core.v_star, "no idea"))
    assert rep.model.final is None and rep.model.silhouette_mismatch is None
    assert rep.model.removed == [] and rep.model.added == []


def test_replay_is_deterministic():
    inst = fixtures.snake_ten_by_ten()
    cert = certify(inst)
    model = evaluate_text(inst, cert.core.v_star, '{"remove":[0,1,2],"add":[10,11,13]}')
    a = build_replay(inst, cert, model).model_dump_json()
    b = build_replay(inst, cert, model).model_dump_json()
    assert a == b
