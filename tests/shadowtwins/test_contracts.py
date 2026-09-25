import json
from pathlib import Path

import pytest

from benchcore import registry
from benchcore.contracts import CompletionMeta, FinishReason
from shadowtwins import fixtures
from shadowtwins.contract_export import SCHEMA_MODELS, export_contracts, versions_document
from shadowtwins.contracts import (
    ShadowTwinsCertificate,
    ShadowTwinsEvaluation,
    ShadowTwinsInstance,
    ShadowTwinsReplay,
)

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "contracts" / "fixtures"


def test_committed_schemas_match_models():
    assert export_contracts(ROOT / "contracts", check=True) == [], (
        "contract drift: run `uv run shadowtwins export-contracts` and record a decision entry")


def test_versions_document_hashes_every_schema():
    doc = json.loads((ROOT / "contracts" / "VERSIONS.json").read_text(encoding="utf-8"))
    assert doc == versions_document()
    assert set(doc["schemas"]) == set(SCHEMA_MODELS)


def test_instance_hash_is_enforced():
    inst = fixtures.bent_tunnel_block()
    doc = inst.model_dump(mode="json")
    doc["core"]["budget"] = 2
    with pytest.raises(ValueError, match="content_hash"):
        ShadowTwinsInstance.model_validate(doc)
    # meta is not part of identity
    doc = inst.model_dump(mode="json")
    doc["meta"]["label"] = "renamed"
    assert ShadowTwinsInstance.model_validate(doc).content_hash == inst.content_hash


def test_committed_fixtures_load_and_reproduce():
    index = json.loads((FIX / "index.json").read_text(encoding="utf-8"))
    module = registry.get("shadow_twins")
    for entry in index["instances"]:
        inst = ShadowTwinsInstance.model_validate_json((FIX / entry["instance"]).read_text(encoding="utf-8"))
        cert = ShadowTwinsCertificate.model_validate_json((FIX / entry["certificate"]).read_text(encoding="utf-8"))
        assert cert.independent_verification.status == "verified"
        assert module.certify(inst).core_hash == cert.core_hash
        prompt = (FIX / entry["prompt"]).read_text(encoding="utf-8").rstrip("\n")
        assert module.render_prompt(inst).messages[0].content == prompt
    for entry in index["responses"]:
        resp = json.loads((FIX / entry["response"]).read_text(encoding="utf-8"))
        inst = ShadowTwinsInstance.model_validate_json(
            (FIX / "instances" / f"{resp['instance_id']}.json").read_text(encoding="utf-8"))
        cert = ShadowTwinsCertificate.model_validate_json(
            (FIX / "certificates" / f"{resp['instance_id']}.json").read_text(encoding="utf-8"))
        env = module.evaluate(inst, cert, resp["raw_text"], CompletionMeta(**resp["completion_meta"]))
        stored = ShadowTwinsEvaluation.model_validate_json((FIX / entry["evaluation"]).read_text(encoding="utf-8"))
        assert env.detail == stored.model_dump(mode="json")
        assert env.category == entry["category"] and env.score == entry["score"]
        ShadowTwinsReplay.model_validate_json((FIX / entry["replay"]).read_text(encoding="utf-8"))


def test_fixture_categories_cover_every_invalid_category():
    index = json.loads((FIX / "index.json").read_text(encoding="utf-8"))
    cats = {e["category"] for e in index["responses"]}
    expected = {"malformed_json", "invalid_ids_or_types", "duplicate_ids", "wrong_source_occupancy",
                "unequal_edit_counts", "budget_exceeded", "silhouette_changed", "solid_disconnected",
                "refusal", "truncated", None}
    assert expected <= cats  # immutable_cell_modified is unreachable through ID answers


def test_module_interface_roundtrip():
    module = registry.get("shadow_twins")
    assert registry.available() == ["shadow_twins"]
    meta = module.metadata()
    assert meta.benchmark_id == "shadow_twins" and "v_star" in meta.score.formula
    inst = fixtures.bent_tunnel_shadow_gate()
    cert = module.certify(inst)
    report = module.independently_verify(inst, cert)
    assert report.status == "verified"
    env = module.evaluate(inst, cert, '{"remove":[1],"add":[2]}', CompletionMeta(finish_reason=FinishReason.STOP))
    assert env.valid and env.score == 50.0 and env.raw_objective == 1 and env.max_objective == 2
    rep = module.build_replay(inst, cert, env)
    assert rep.model.score == 50.0
    assert module.validate_instance(inst).ok
    zero = fixtures.straight_tunnel_zero()
    with pytest.raises(ValueError, match="inadmissible"):
        module.evaluate(zero, module.certify(zero), "{}")


def test_prompt_contains_no_solution_information():
    module = registry.get("shadow_twins")
    inst = fixtures.snake_ten_by_ten()
    cert = module.certify(inst)
    text = module.render_prompt(inst).messages[0].content.lower()
    for forbidden in ("optimum", "optimal", "v_star", "v*", "witness", "certif", "score"):
        assert forbidden not in text
    w = cert.core.best_witness
    assert json.dumps({"remove": w.remove, "add": w.add}, separators=(",", ":")) not in text
