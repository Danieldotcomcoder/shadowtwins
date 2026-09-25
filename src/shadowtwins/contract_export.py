"""Export versioned JSON Schemas and authoritative development fixtures for P2-P4.

``contracts/schemas/*.schema.json`` are generated from the Pydantic models; their sha256 hashes are
recorded in ``contracts/VERSIONS.json`` and checked in CI (``shadowtwins export-contracts --check``).
``contracts/fixtures/`` holds formal fixture instances, verified certificates, sample raw responses
covering every answer category, and the evaluations and replays they produce. Fixture data is
formal test material, never benchmark results.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from benchcore import contracts as bc
from benchcore.hashing import sha256_text

from . import contracts as st
from . import evaluate as ev
from . import fixtures, replay, solver, versions
from .module import ShadowTwinsModule, attach_verification

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "shadowtwins.instance.v1": st.ShadowTwinsInstance,
    "shadowtwins.certificate.v1": st.ShadowTwinsCertificate,
    "shadowtwins.evaluation.v1": st.ShadowTwinsEvaluation,
    "shadowtwins.replay.v1": st.ShadowTwinsReplay,
    "shadowtwins.parse-outcome.v1": st.ParseOutcome,
    "shadowtwins.edit.v1": st.Edit,
    "benchcore.evaluation-envelope.v1": bc.EvaluationEnvelope,
    "benchcore.rendered-prompt.v1": bc.RenderedPrompt,
    "benchcore.run-spec.v1": bc.RunSpec,
    "benchcore.benchmark-metadata.v1": bc.BenchmarkMetadata,
}


def _schema_text(model: type[BaseModel]) -> str:
    return json.dumps(model.model_json_schema(mode="serialization"), indent=2, sort_keys=True) + "\n"


def _write_if_changed(path: Path, text: str, check: bool, changed: list[str]) -> None:
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old != text:
        changed.append(str(path.name))
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")


def versions_document() -> dict[str, Any]:
    return {
        "contracts_version": bc.CONTRACTS_VERSION,
        "suite": {"id": bc.SUITE_ID, "version": bc.SUITE_VERSION,
                  "benchmarks": list(bc.SUITE_BENCHMARKS)},
        "shadow_twins": {
            "rules": versions.RULES_VERSION,
            "parser": versions.PARSER_VERSION,
            "evaluator": versions.EVALUATOR_VERSION,
            "solver": versions.SOLVER_VERSION,
            "protocol": versions.PROTOCOL_VERSION,
            "generator": versions.GENERATOR_VERSION,
            "replay": versions.REPLAY_VERSION,
        },
        "schemas": {name: sha256_text(_schema_text(model)) for name, model in SCHEMA_MODELS.items()},
    }


def export_contracts(root: Path, check: bool = False) -> list[str]:
    changed: list[str] = []
    for name, model in SCHEMA_MODELS.items():
        _write_if_changed(root / "schemas" / f"{name}.schema.json", _schema_text(model), check, changed)
    _write_if_changed(root / "VERSIONS.json",
                      json.dumps(versions_document(), indent=2, sort_keys=True) + "\n", check, changed)
    return changed


# --- fixtures ---------------------------------------------------------------------------------

# (case name, instance id, raw response, finish_reason, provider refusal)
SAMPLE_RESPONSES: list[tuple[str, str, str, str, str | None]] = [
    ("optimal", "fx-shadow-gate", '{"remove":[0],"add":[2]}', "stop", None),
    ("optimal-fenced", "fx-shadow-gate", '```json\n{"add": [3], "remove": [0]}\n```', "stop", None),
    ("partial", "fx-shadow-gate", '{"remove":[1],"add":[2]}', "stop", None),
    ("noop", "fx-shadow-gate", '{"remove":[],"add":[]}', "stop", None),
    ("prose-wrapped", "fx-shadow-gate", 'Answer: {"remove":[0],"add":[2]}', "stop", None),
    ("multiple-answers", "fx-shadow-gate", '{"remove":[0],"add":[2]}\n{"remove":[],"add":[]}', "stop", None),
    ("duplicate-keys", "fx-shadow-gate", '{"remove":[0],"remove":[1],"add":[2]}', "stop", None),
    ("boolean-id", "fx-shadow-gate", '{"remove":[true],"add":[2]}', "stop", None),
    ("float-id", "fx-shadow-gate", '{"remove":[0.0],"add":[2]}', "stop", None),
    ("out-of-range", "fx-shadow-gate", '{"remove":[0],"add":[9]}', "stop", None),
    ("duplicate-ids", "fx-shadow-gate", '{"remove":[0,0],"add":[2,3]}', "stop", None),
    ("wrong-source", "fx-shadow-gate", '{"remove":[2],"add":[0]}', "stop", None),
    ("unequal-counts", "fx-shadow-gate", '{"remove":[0],"add":[]}', "stop", None),
    ("budget-exceeded", "fx-shadow-gate", '{"remove":[0,1],"add":[2,3]}', "stop", None),
    ("silhouette-changed", "fx-shadow-gate", '{"remove":[1],"add":[3]}', "stop", None),
    ("refusal", "fx-shadow-gate", "I can't help with that request.", "stop", None),
    ("provider-refusal", "fx-shadow-gate", "", "content_filter", "Content blocked"),
    ("truncated", "fx-shadow-gate", '{"remove":[0],"a', "length", None),
    ("disconnected", "fx-snake-10x10", '{"remove":[2,4],"add":[10,11]}', "stop", None),
    ("snake-optimal", "fx-snake-10x10", '{"remove":[0,1,2],"add":[10,11,13]}', "stop", None),
]


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def export_fixtures(out: Path) -> int:
    module = ShadowTwinsModule()
    count = 0
    index: dict[str, Any] = {
        "note": "Formal fixtures for development and tests. Not benchmark content or model results.",
        "versions": versions_document()["shadow_twins"],
        "instances": [],
        "responses": [],
    }
    by_id: dict[str, tuple[st.ShadowTwinsInstance, st.ShadowTwinsCertificate]] = {}
    for inst in fixtures.all_fixtures():
        cert = solver.certify(inst)
        cert = attach_verification(cert, module.independently_verify(inst, cert))
        if cert.independent_verification.status != "verified":
            raise RuntimeError(f"fixture {inst.instance_id} failed independent verification")
        by_id[inst.instance_id] = (inst, cert)
        _write_json(out / "instances" / f"{inst.instance_id}.json", inst.model_dump(mode="json"))
        _write_json(out / "certificates" / f"{inst.instance_id}.json", cert.model_dump(mode="json"))
        entry: dict[str, Any] = {
            "instance_id": inst.instance_id,
            "label": inst.meta.label,
            "v_star": cert.core.v_star,
            "admissible": cert.core.admissible,
            "instance": f"instances/{inst.instance_id}.json",
            "certificate": f"certificates/{inst.instance_id}.json",
            "prompt": f"prompts/{inst.instance_id}.txt",
        }
        (out / "prompts").mkdir(parents=True, exist_ok=True)
        (out / "prompts" / f"{inst.instance_id}.txt").write_text(
            module.render_prompt(inst).messages[0].content + "\n", encoding="utf-8")
        count += 3
        if cert.core.admissible:
            rep = replay.build_replay(inst, cert, None)
            _write_json(out / "replays" / f"{inst.instance_id}__optimal-only.json", rep.model_dump(mode="json"))
            entry["replay"] = f"replays/{inst.instance_id}__optimal-only.json"
            count += 1
        index["instances"].append(entry)

    for case, iid, raw, finish, refusal in SAMPLE_RESPONSES:
        inst, cert = by_id[iid]
        meta = bc.CompletionMeta(finish_reason=bc.FinishReason(finish), refusal=refusal)
        evaluation = ev.evaluate_text(inst, cert.core.v_star, raw, meta)
        rep = replay.build_replay(inst, cert, evaluation)
        stem = f"{iid}__{case}"
        _write_json(out / "responses" / f"{stem}.json",
                    {"instance_id": iid, "case": case, "raw_text": raw,
                     "completion_meta": meta.model_dump(mode="json")})
        _write_json(out / "evaluations" / f"{stem}.json", evaluation.model_dump(mode="json"))
        _write_json(out / "replays" / f"{stem}.json", rep.model_dump(mode="json"))
        index["responses"].append({
            "case": case, "instance_id": iid, "valid": evaluation.valid,
            "category": evaluation.category.value if evaluation.category else None,
            "score": evaluation.score,
            "response": f"responses/{stem}.json",
            "evaluation": f"evaluations/{stem}.json",
            "replay": f"replays/{stem}.json",
        })
        count += 3
    _write_json(out / "index.json", index)
    return count + 1
