import random

import pytest

from shadowtwins import fixtures
from shadowtwins.contracts import Edit, InstanceMeta, ShadowTwinsInstance
from shadowtwins.evaluate import evaluate_edit
from shadowtwins.solver import certify
from shadowtwins.transforms import (
    IDENTITY,
    SYMMETRIES,
    apply_to_coord,
    instance_canonical_key,
    transform_instance,
)

INVARIANT_FIELDS = [
    "budget", "solid_editable", "empty_editable", "expected_enumerated_count", "enumerated_count",
    "legal_count", "v_star", "v_min", "optimal_count", "min_moves_for_optimum", "histogram",
    "histogram_by_moves", "best_witness", "worst_witness", "rejections", "constraint_totals",
    "no_shadow", "admissible",
]


def _core(inst):
    return certify(inst).core.model_dump(mode="json")


def test_48_distinct_symmetries():
    assert len(SYMMETRIES) == 48
    images = {tuple(apply_to_coord(s, c) for c in [(0, 1, 2), (1, 0, 3), (3, 2, 0)]) for s in SYMMETRIES}
    assert len(images) == 48
    assert SYMMETRIES[0] == IDENTITY


@pytest.mark.parametrize("fx", [fixtures.bent_tunnel_shadow_gate(), fixtures.straight_tunnel_zero()],
                         ids=lambda i: i.instance_id)
def test_certificate_invariant_under_all_symmetries(fx):
    base = _core(fx)
    for k, sym in enumerate(SYMMETRIES):
        other = _core(transform_instance(fx, sym, suffix=f"s{k}"))
        for field in INVARIANT_FIELDS:
            assert other[field] == base[field], (sym, field)


def test_certificate_invariant_under_symmetries_large():
    fx = fixtures.snake_ten_by_ten()
    base = _core(fx)
    for sym in random.Random(5).sample(SYMMETRIES, 6):
        other = _core(transform_instance(fx, sym))
        for field in INVARIANT_FIELDS:
            assert other[field] == base[field], (sym, field)


def test_editable_label_permutation_preserves_extrema():
    fx = fixtures.snake_ten_by_ten()
    base = certify(fx).core
    rng = random.Random(9)
    perm = list(range(len(fx.core.editable)))
    rng.shuffle(perm)  # new ID j refers to old ID perm[j]
    permuted = ShadowTwinsInstance.build(
        "perm", fx.core.occupancy, list(fx.core.entrances), [fx.core.editable[perm[j]] for j in range(len(perm))],
        fx.core.budget, InstanceMeta())
    other = certify(permuted).core
    for field in ("legal_count", "v_star", "optimal_count", "histogram", "enumerated_count", "min_moves_for_optimum"):
        assert getattr(other, field) == getattr(base, field)
    # the old optimum, relabelled, is still optimal
    inv = {old: new for new, old in enumerate(perm)}
    w = base.best_witness
    relabelled = Edit(remove=[inv[k] for k in w.remove], add=[inv[k] for k in w.add])
    res = evaluate_edit(permuted, other.v_star, relabelled)
    assert res.valid and res.raw_objective == other.v_star


def test_entrance_order_permutation_preserves_extrema():
    fx = fixtures.snake_ten_by_ten()
    base = certify(fx).core
    ents = list(fx.core.entrances)[::-1]
    other = certify(ShadowTwinsInstance.build("rev", fx.core.occupancy, ents, list(fx.core.editable),
                                              fx.core.budget, InstanceMeta())).core
    assert other.histogram == base.histogram and other.best_witness == base.best_witness


def test_canonical_key_identifies_symmetric_duplicates():
    fx = fixtures.bent_tunnel_shadow_gate()
    key = instance_canonical_key(fx)
    for sym in SYMMETRIES[::7]:
        assert instance_canonical_key(transform_instance(fx, sym)) == key
    assert instance_canonical_key(fixtures.bent_tunnel_block()) != key
