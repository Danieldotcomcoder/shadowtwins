import dataclasses
import random

import pytest

from benchcore.contracts import CompletionMeta, FinishReason
from shadowtwins import fixtures, grid
from shadowtwins.contracts import (
    CheckCode,
    CheckStatus,
    Edit,
    InstanceMeta,
    InvalidCategory,
    ShadowTwinsInstance,
)
from shadowtwins.engine import compile_instance
from shadowtwins.evaluate import evaluate_edit, evaluate_text, validate_edit
from shadowtwins.solver import certify
from stverify.core import Puzzle, evaluate_answer

from .randinst import random_instances

GATE = fixtures.bent_tunnel_shadow_gate()
GATE_VSTAR = 2


def ev(raw, inst=GATE, v_star=GATE_VSTAR, **meta):
    return evaluate_text(inst, v_star, raw, CompletionMeta(**meta) if meta else None)


def test_hand_checked_shadow_gate_answers():
    # remove gate (3,2,1), fill tunnel (1,1,1): A-B closed, B-C opened -> v = 2
    r = ev('{"remove":[0],"add":[2]}')
    assert r.valid and r.raw_objective == 2 and r.opened == 1 and r.closed == 1
    assert r.score == 100.0 and r.is_optimal
    # remove gate, fill cavity: A-C and B-C opened -> v = 2
    r = ev('{"remove":[0],"add":[3]}')
    assert r.valid and (r.opened, r.closed) == (2, 0) and r.score == 100.0
    # move (3,1,1) onto the same x-ray at (1,1,1): legal, closes A-B only -> v = 1
    r = ev('{"remove":[1],"add":[2]}')
    assert r.valid and r.raw_objective == 1 and r.score == 50.0 and not r.is_optimal
    # move (3,1,1) off its ray into the cavity: the x silhouette loses pixel (y=1, z=1)
    r = ev('{"remove":[1],"add":[3]}')
    assert not r.valid and r.category == InvalidCategory.SILHOUETTE_CHANGED and r.score == 0
    sil = next(c for c in r.checks if c.code == CheckCode.SILHOUETTE_X)
    assert sil.status == CheckStatus.FAIL and "(y=1,z=1) lost" in sil.message
    assert (3, 1, 1) in [tuple(c) for c in sil.cells]


def test_noop_is_valid_zero_and_distinct_from_invalid():
    noop = ev('{"remove":[],"add":[]}')
    bad = ev('{"remove":[0],"add":[]}')
    assert noop.valid and noop.score == 0 and noop.raw_objective == 0 and noop.category is None
    assert not bad.valid and bad.score == 0 and bad.category == InvalidCategory.UNEQUAL_EDIT_COUNTS
    assert noop.move_count == 0


@pytest.mark.parametrize(
    "raw, category",
    [
        ('{"remove":[0],"add":[4]}', InvalidCategory.INVALID_IDS_OR_TYPES),
        ('{"remove":[-1],"add":[2]}', InvalidCategory.INVALID_IDS_OR_TYPES),
        ('{"remove":[true],"add":[2]}', InvalidCategory.INVALID_IDS_OR_TYPES),
        ('{"remove":[0,0],"add":[2,3]}', InvalidCategory.DUPLICATE_IDS),
        ('{"remove":[0],"add":[0]}', InvalidCategory.DUPLICATE_IDS),
        ('{"remove":[2],"add":[3]}', InvalidCategory.WRONG_SOURCE_OCCUPANCY),
        ('{"remove":[0],"add":[1]}', InvalidCategory.WRONG_SOURCE_OCCUPANCY),
        ('{"remove":[3],"add":[2]}', InvalidCategory.WRONG_SOURCE_OCCUPANCY),
        ('{"remove":[0,1],"add":[2]}', InvalidCategory.UNEQUAL_EDIT_COUNTS),
        ('{"remove":[0,1],"add":[2,3]}', InvalidCategory.BUDGET_EXCEEDED),
        ('{"remove":[1],"add":[3]}', InvalidCategory.SILHOUETTE_CHANGED),
        ("The best move is 0 to 2.", InvalidCategory.MALFORMED_JSON),
    ],
)
def test_invalid_categories(raw, category):
    r = ev(raw)
    assert not r.valid and r.category == category and r.score == 0.0 and r.raw_objective is None


def test_wrong_source_occupancy_both_directions():
    r = ev('{"remove":[2],"add":[1]}')  # remove an empty cell, add onto a solid cell
    assert r.category == InvalidCategory.WRONG_SOURCE_OCCUPANCY
    chk = next(c for c in r.checks if c.code == CheckCode.SOURCE_OCCUPANCY)
    assert chk.ids == [1, 2]


def test_budget_counts_relocations_not_bits():
    # b = 1: a single relocation changes two occupancy bits but uses one move.
    assert ev('{"remove":[0],"add":[2]}').valid


def test_solid_disconnected():
    occ = grid.FULL
    for c in [*fixtures.BENT_TUNNEL, (3, 0, 3), (2, 3, 3), (3, 2, 3)]:
        occ &= ~(1 << grid.index(*c))
    inst = ShadowTwinsInstance.build("t-disc", occ, [(0, 1, 1), (2, 3, 1)], [(3, 3, 2), (1, 1, 1)], 1,
                                     InstanceMeta(split="fixture"))
    r = evaluate_text(inst, 1, '{"remove":[0],"add":[1]}')
    assert r.category == InvalidCategory.SOLID_DISCONNECTED
    chk = next(c for c in r.checks if c.code == CheckCode.SOLID_CONNECTED)
    assert [tuple(c) for c in chk.cells] == [(3, 3, 3)]
    # silhouettes still pass: disconnection is reported on its own
    assert all(c.status == CheckStatus.PASS for c in r.checks if c.code.value.startswith("silhouette"))


def test_immutable_cell_check_on_tampered_compiled_instance():
    # IDs can only address editable cells, so this category needs a tampered editable list.
    c = compile_instance(GATE)
    entrance = c.entrances[0]
    tampered = dataclasses.replace(c, editable=(*c.editable[:3], entrance),
                                   editable_mask=c.editable_mask)
    val = validate_edit(tampered, Edit(remove=[0], add=[3]))
    assert val.category == InvalidCategory.IMMUTABLE_CELL_MODIFIED


def test_truncated_and_refusal_categories():
    assert ev('{"remove":[0', finish_reason=FinishReason.LENGTH).category == InvalidCategory.TRUNCATED
    assert ev("I cannot help with this.").category == InvalidCategory.REFUSAL


def test_zero_optimum_instances_cannot_be_scored():
    with pytest.raises(ValueError):
        evaluate_text(fixtures.straight_tunnel_zero(), 0, '{"remove":[],"add":[]}')


def test_every_check_reported_for_inspection():
    r = ev('{"remove":[1],"add":[3]}')
    codes = [c.code for c in r.checks]
    assert codes[0] == CheckCode.PARSE and len(codes) == 11
    parse_fail = ev("nope")
    assert all(c.status == CheckStatus.SKIPPED for c in parse_fail.checks[1:])


def test_score_boundaries_on_all_fixture_candidates():
    inst = fixtures.snake_ten_by_ten()
    cert = certify(inst)
    v_star = cert.core.v_star
    rng = random.Random(1)
    c = compile_instance(inst)
    for _ in range(300):
        r = rng.randrange(0, 4)
        edit = Edit(remove=sorted(rng.sample(c.solid_ids, r)), add=sorted(rng.sample(c.empty_ids, r)))
        res = evaluate_edit(inst, v_star, edit, c)
        assert 0.0 <= res.score <= 100.0
        if res.valid:
            assert res.score == pytest.approx(100.0 * res.raw_objective / v_star)


def test_evaluator_agrees_with_independent_verifier_on_random_answers():
    rng = random.Random(11)
    insts = random_instances(5, 12, n_solid=5, n_empty=5, budget=2)
    for inst in insts:
        p = Puzzle(inst.model_dump(mode="json"))
        c = compile_instance(inst)
        n = len(inst.core.editable)
        for _ in range(120):
            rem = [rng.randrange(-1, n + 1) for _ in range(rng.randrange(0, 4))]
            add = [rng.randrange(-1, n + 1) for _ in range(rng.randrange(0, 4))]
            mine = evaluate_edit(inst, 99, Edit(remove=rem, add=add), c)
            ref = evaluate_answer(p, rem, add)
            assert mine.valid == ref["valid"], (rem, add, mine.category, ref)
            if mine.valid:
                assert mine.raw_objective == ref["objective"]
                assert (mine.opened, mine.closed) == (ref["opened"], ref["closed"])
            else:
                assert mine.category is not None and mine.category.value in ref["reasons"]
