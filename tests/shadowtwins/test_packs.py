import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

from benchcore.hashing import content_hash
from shadowtwins import fixtures
from shadowtwins.ablation import evaluate_no_shadow, render_prompt_no_shadow
from shadowtwins.baselines import local_search, random_legal_expectation
from shadowtwins.contracts import Edit
from shadowtwins.engine import compile_instance
from shadowtwins.evaluate import evaluate_edit, evaluate_text
from shadowtwins.generator import GeneratorParams, generate_candidate
from shadowtwins.packs import PREFIX, load_pack, pack_versions
from shadowtwins.policy import TIER_BY_ID, admission_failures, matches_tier, policy_document
from shadowtwins.solver import certify, iter_candidates
from shadowtwins.transforms import geometry_key

ROOT = Path(__file__).resolve().parents[2]
PACKS = ROOT / "packs"
PACK_IDS = ["shadowtwins-dev-v1", "shadowtwins-practice-v1", "shadowtwins-ranked-v1"]
HAS_TOKENIZERS = all(importlib.util.find_spec(m) for m in ("tiktoken", "tokenizers"))


def test_generator_is_deterministic():
    a = generate_candidate(12345, GeneratorParams(budget=2))
    b = generate_candidate(12345, GeneratorParams(budget=2))
    c = generate_candidate(12346, GeneratorParams(budget=2))
    assert a is not None and b is not None and c is not None
    assert a.content_hash == b.content_hash != c.content_hash
    assert a.meta.seed == 12345 and a.meta.generator_version


def test_generated_candidates_are_structurally_valid():
    from shadowtwins.engine import structural_problems

    made = 0
    for seed in range(60):
        inst = generate_candidate(seed, GeneratorParams(budget=1 + seed % 3))
        if inst is None:
            continue
        made += 1
        assert structural_problems(inst) == []
        occ = inst.occupancy_mask
        eds = inst.editable_indices
        solid = [i for i in eds if (occ >> i) & 1]
        assert eds == sorted(solid) + sorted(i for i in eds if not (occ >> i) & 1)
    assert made > 40


def test_local_search_returns_a_legal_edit_with_its_true_objective():
    inst = fixtures.snake_ten_by_ten()
    c = compile_instance(inst)
    cert = certify(inst)
    res = local_search(c)
    ev = evaluate_edit(inst, cert.core.v_star, Edit(remove=list(res.edit[0]), add=list(res.edit[1])), c)
    assert ev.valid and ev.raw_objective == res.objective <= cert.core.v_star
    assert res.evaluations <= 400


def test_local_search_is_exhaustive_for_single_moves():
    for seed in range(40):
        inst = generate_candidate(seed, GeneratorParams(budget=1))
        if inst is None:
            continue
        cert = certify(inst)
        assert local_search(compile_instance(inst)).objective == cert.core.v_star


def test_random_legal_expectation_matches_enumeration():
    inst = fixtures.snake_ten_by_ten()
    cert = certify(inst)
    c = compile_instance(inst)
    from shadowtwins.baselines import legal_value

    values = [v for r, rm, ad, _ in iter_candidates(c) if (v := legal_value(c, (rm, ad))) is not None]
    exp = random_legal_expectation(cert)
    assert exp["random_legal_expected_score"] == pytest.approx(
        100 * sum(values) / len(values) / cert.core.v_star)
    assert exp["random_candidate_valid_probability"] == pytest.approx(len(values) / cert.core.enumerated_count)


def test_admission_rules():
    good = {"v_star": 5, "partial_levels": [2], "optimum_density": 0.1, "shadow_rejection_rate": 0.4,
            "shadow_traps": 3, "tokens_max": 650, "budget": 2, "min_moves_for_optimum": 2,
            "local_search_score": 100.0}
    assert admission_failures(good) == []
    assert admission_failures({**good, "v_star": 1}) == ["v_star_below_min"]
    assert admission_failures({**good, "partial_levels": []}) == ["no_partial_credit"]
    assert admission_failures({**good, "shadow_rejection_rate": 0.1}) == ["shadow_inactive"]
    assert admission_failures({**good, "shadow_traps": 0}) == ["no_shadow_traps"]
    assert admission_failures({**good, "optimum_density": 0.5}) == ["optimum_too_dense"]
    assert admission_failures({**good, "tokens_max": 801}) == ["token_ceiling"]
    assert matches_tier(good, TIER_BY_ID["T2"])
    assert not matches_tier(good, TIER_BY_ID["T1"])
    assert matches_tier({**good, "budget": 3, "min_moves_for_optimum": 2, "local_search_score": 50.0},
                        TIER_BY_ID["T3"])
    assert not matches_tier({**good, "budget": 3, "min_moves_for_optimum": 2}, TIER_BY_ID["T3"])


@pytest.mark.parametrize("pack_id", PACK_IDS)
def test_pack_integrity(pack_id):
    manifest, items = load_pack(PACKS / pack_id)
    policy = json.loads((PACKS / pack_id / "policy.json").read_text(encoding="utf-8"))
    assert policy == policy_document(), "pack was built under a different policy version"
    assert manifest["policy_hash"] == policy["policy_hash"]
    assert manifest["versions"] == pack_versions()
    identity = {
        "pack_id": manifest["pack_id"], "split": manifest["split"], "benchmark_id": manifest["benchmark_id"],
        "versions": manifest["versions"], "policy_hash": manifest["policy_hash"],
        "items": [{k: it[k] for k in ("order", "instance_id", "tier", "content_hash",
                                      "certificate_core_hash", "v_star")} for it in manifest["items"]],
    }
    assert content_hash(identity) == manifest["pack_hash"]
    target = policy["selection"]["per_tier"][manifest["split"]]
    assert Counter(it["tier"] for _, _, it in items) == {"T1": target, "T2": target, "T3": target}
    for inst, cert, it in items:
        assert cert.independent_verification.status == "verified"
        assert cert.core.admissible and cert.core.v_star >= 2
        assert inst.meta.split == manifest["split"] and inst.meta.tier == it["tier"]
        assert inst.core.budget == TIER_BY_ID[it["tier"]].budget
        assert it["tokens_max"] <= 800


@pytest.mark.parametrize("pack_id", PACK_IDS)
def test_pack_items_satisfy_frozen_policy(pack_id):
    rows = json.loads((PACKS / pack_id / "reports" / "metrics.json").read_text(encoding="utf-8"))
    for row in rows:
        m = row["metrics"]
        assert admission_failures(m) == [], row["instance_id"]
        assert matches_tier(m, TIER_BY_ID[row["tier"]]), row["instance_id"]


def test_ranked_pack_regenerates_from_seeds():
    _, items = load_pack(PACKS / "shadowtwins-ranked-v1")
    for inst, _cert, it in items:
        tier = TIER_BY_ID[it["tier"]]
        regen = generate_candidate(it["seed"], GeneratorParams(budget=tier.budget, split="ranked",
                                                               id_prefix=PREFIX["ranked"]))
        assert regen is not None and regen.content_hash == inst.content_hash
    # spot-check exact recertification (core hash identical)
    for inst, cert, _it in items[:12]:
        assert certify(inst).core_hash == cert.core_hash


def test_no_duplicate_geometry_and_disjoint_splits():
    keys: dict[str, str] = {}
    seeds: dict[int, str] = {}
    for pack_id in PACK_IDS:
        _, items = load_pack(PACKS / pack_id)
        for inst, _, it in items:
            k = geometry_key(inst.occupancy_mask, inst.entrance_indices)
            assert k not in keys, f"{inst.instance_id} duplicates {keys.get(k)}"
            keys[k] = inst.instance_id
            assert it["seed"] not in seeds
            seeds[it["seed"]] = pack_id


def test_ablation_prompt_and_scoring():
    inst = fixtures.bent_tunnel_shadow_gate()
    cert = certify(inst)
    prompt = render_prompt_no_shadow(inst).messages[0].content
    assert "shadows" not in prompt and "2. All solid cubes as one piece" in prompt
    # silhouette-illegal in the official task, legal in the ablation
    official = evaluate_text(inst, cert.core.v_star, '{"remove":[1],"add":[3]}')
    ablation = evaluate_no_shadow(inst, cert, '{"remove":[1],"add":[3]}')
    assert not official.valid and ablation.valid
    assert ablation.v_star == cert.core.no_shadow.v_star
    assert ablation.score == 100.0 * ablation.raw_objective / ablation.v_star
    # other rules still apply
    assert not evaluate_no_shadow(inst, cert, '{"remove":[0],"add":[]}').valid
    assert not evaluate_no_shadow(inst, cert, "nope").valid


@pytest.mark.skipif(not HAS_TOKENIZERS, reason="research extra not installed")
def test_token_panel_counts_are_frozen():
    from shadowtwins.prompt import render_prompt
    from shadowtwins.tokens import count_messages

    try:
        report = count_messages(render_prompt(fixtures.bent_tunnel_shadow_gate()).messages)
    except OSError as exc:  # pragma: no cover - offline without a tokenizer cache
        pytest.skip(f"tokenizer files unavailable: {exc}")
    assert report["counts"] == {"openai-o200k": 436, "openai-cl100k": 436, "llama-3.1": 436,
                                "qwen-2.5": 468, "deepseek-v3": 441, "mistral-nemo": 471, "phi-3.5": 513}
    assert report["max"] == 513 and report["within_ceiling"]
