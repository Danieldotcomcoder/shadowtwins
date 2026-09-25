import json
from math import comb

import pytest

from shadowtwins import fixtures
from shadowtwins.contracts import Edit, ShadowTwinsCertificate
from shadowtwins.engine import compile_instance
from shadowtwins.evaluate import evaluate_edit
from shadowtwins.solver import certify, expected_candidate_count
from stverify import compare_certificate

from .randinst import random_instances


def test_candidate_count_formula():
    assert expected_candidate_count(10, 10, 3) == 16_526
    assert expected_candidate_count(10, 10, 3) == 1 + 100 + 45 * 45 + 120 * 120
    assert expected_candidate_count(3, 1, 3) == 1 + 3
    assert expected_candidate_count(0, 5, 3) == 1  # only the no-op
    for s in range(6):
        for e in range(6):
            for b in range(1, 4):
                assert expected_candidate_count(s, e, b) == sum(
                    comb(s, r) * comb(e, r) for r in range(min(b, s, e) + 1))


def test_bent_tunnel_block_hand_values():
    c = certify(fixtures.bent_tunnel_block()).core
    assert (c.enumerated_count, c.legal_count, c.v_star, c.v_min) == (4, 4, 1, 0)
    assert c.histogram == {"0": 1, "1": 3}
    assert c.optimal_count == 3 and c.min_moves_for_optimum == 1
    assert (c.best_witness.remove, c.best_witness.add) == ([1], [0])
    assert (c.worst_witness.remove, c.worst_witness.add) == ([], [])
    assert c.rejections.silhouette == 0 and c.rejections.solid_disconnected == 0
    assert c.admissible


def test_shadow_gate_hand_values():
    c = certify(fixtures.bent_tunnel_shadow_gate()).core
    assert (c.solid_editable, c.empty_editable) == (2, 2)
    assert (c.enumerated_count, c.legal_count, c.v_star) == (5, 4, 2)
    assert c.histogram == {"0": 1, "1": 1, "2": 2}
    assert c.histogram_by_moves == {"0": {"0": 1}, "1": {"1": 1, "2": 2}}
    assert c.optimal_count == 2
    assert (c.best_witness.remove, c.best_witness.add, c.best_witness.objective) == ([0], [2], 2)
    assert c.rejections.silhouette == 1 and c.rejections.solid_disconnected == 0
    assert c.no_shadow.legal_count == 5 and c.no_shadow.v_star == 2
    assert c.no_shadow.histogram == {"0": 2, "1": 1, "2": 2}


def test_zero_optimum_is_inadmissible_and_shadow_matters():
    c = certify(fixtures.straight_tunnel_zero()).core
    assert c.v_star == 0 and not c.admissible and c.inadmissible_reason
    assert c.legal_count == 3 and c.histogram == {"0": 3}
    assert c.rejections.silhouette == 2
    assert c.constraint_totals.model_dump() == {"silhouette_fail": 2, "solid_disconnected": 1, "both": 1}
    # Without the silhouette rule, filling the tunnel would close A-B.
    assert c.no_shadow.v_star == 1
    assert (c.no_shadow.best_witness.remove, c.no_shadow.best_witness.add) == ([2], [1])


def test_ten_by_ten_enumeration_count_and_witness():
    inst = fixtures.snake_ten_by_ten()
    cert = certify(inst)
    c = cert.core
    assert (c.solid_editable, c.empty_editable, c.budget) == (10, 10, 3)
    assert c.enumerated_count == c.expected_enumerated_count == 16_526
    assert sum(c.histogram.values()) == c.legal_count
    assert sum(sum(h.values()) for h in c.histogram_by_moves.values()) == c.legal_count
    assert c.legal_count + c.rejections.silhouette + c.rejections.solid_disconnected == c.enumerated_count
    w = c.best_witness
    res = evaluate_edit(inst, c.v_star, Edit(remove=w.remove, add=w.add))
    assert res.valid and res.raw_objective == c.v_star == w.objective


def test_certificate_is_deterministic():
    inst = fixtures.snake_ten_by_ten()
    a, b = certify(inst), certify(inst)
    assert a.core_hash == b.core_hash
    assert a.core == b.core


def test_witness_alone_is_not_optimality_proof():
    # The certificate is exhaustive; every legal candidate is at or below the optimum.
    inst = fixtures.bent_tunnel_shadow_gate()
    c = certify(inst).core
    assert c.exhaustive is True
    assert max(int(k) for k in c.histogram) == c.v_star


@pytest.mark.parametrize("fx", fixtures.all_fixtures(), ids=lambda i: i.instance_id)
def test_independent_verifier_agrees_on_fixtures(fx):
    cert = certify(fx)
    result = compare_certificate(fx.model_dump(mode="json"), cert.model_dump(mode="json"))
    assert result["mismatches"] == []


def test_independent_verifier_agrees_on_random_instances():
    for inst in random_instances(2024, 20, n_solid=5, n_empty=5, budget=2):
        cert = certify(inst)
        result = compare_certificate(inst.model_dump(mode="json"), cert.model_dump(mode="json"))
        assert result["mismatches"] == [], inst.instance_id


def test_independent_verifier_agrees_on_budget_three_random():
    for inst in random_instances(77, 4, n_solid=6, n_empty=6, budget=3):
        cert = certify(inst)
        assert compare_certificate(inst.model_dump(mode="json"), cert.model_dump(mode="json"))["mismatches"] == []


def test_verifier_detects_tampering():
    inst = fixtures.bent_tunnel_shadow_gate()
    good = certify(inst).model_dump(mode="json")

    def tampered(mutate):
        doc = json.loads(json.dumps(good))
        mutate(doc["core"])
        return compare_certificate(inst.model_dump(mode="json"), doc)["mismatches"]

    def bump(core):
        core["v_star"] = 3
    assert any("v_star" in m for m in tampered(bump))

    def hist(core):
        core["histogram"]["1"] = 2
    assert tampered(hist)

    def witness(core):
        core["best_witness"] = {"remove": [1], "add": [2], "objective": 2}
    assert any("best_witness" in m for m in tampered(witness))

    # A consistent hash on a wrong core is still caught by recomputation.
    doc = json.loads(json.dumps(good))
    doc["core"]["legal_count"] = 5
    from benchcore.hashing import content_hash
    doc["core_hash"] = content_hash(doc["core"])
    assert any("legal_count" in m for m in compare_certificate(inst.model_dump(mode="json"), doc)["mismatches"])


def test_certificate_hash_guard():
    cert = certify(fixtures.bent_tunnel_block())
    doc = cert.model_dump(mode="json")
    doc["core"]["v_star"] = 7
    with pytest.raises(ValueError):
        ShadowTwinsCertificate.model_validate(doc)


def test_compile_rejects_structurally_invalid_instances():
    from shadowtwins import grid
    from shadowtwins.contracts import InstanceMeta, ShadowTwinsInstance

    solid_entrance = ShadowTwinsInstance.build("bad", grid.FULL, [(0, 0, 0), (3, 3, 3)], [(1, 1, 1)], 1,
                                               InstanceMeta())
    with pytest.raises(ValueError, match="is solid"):
        compile_instance(solid_entrance)
    disconnected = grid.mask_of([0, 63])
    inst = ShadowTwinsInstance.build("bad2", disconnected, [(1, 0, 0), (2, 0, 0)], [(0, 1, 0)], 1,
                                     InstanceMeta())
    with pytest.raises(ValueError, match="face-connected"):
        compile_instance(inst)
    interior = ShadowTwinsInstance.build("bad3", grid.FULL & ~(1 << grid.index(1, 1, 1)) & ~1,
                                         [(1, 1, 1), (0, 0, 0)], [(2, 2, 2)], 1, InstanceMeta())
    with pytest.raises(ValueError, match="boundary"):
        compile_instance(interior)
