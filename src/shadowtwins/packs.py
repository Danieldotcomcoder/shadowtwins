"""Development reports and immutable benchmark packs (P2).

Pack layout (``packs/<pack_id>/``)::

    manifest.json              identity, versions, policy hash, tiers, items with file hashes
    instances/<id>.json        ShadowTwinsInstance
    certificates/<id>.json     ShadowTwinsCertificate with independent verification recorded
    reports/metrics.json       per-instance measurements (shadow activity, densities, baselines)
    reports/tokens.json        per-instance counts under the frozen tokenizer panel
    reports/baselines.json     baseline scores per instance, per tier and pack (tier-equal mean)

``pack_hash`` covers the deterministic identity (versions, policy hash, ordered items with
instance content hashes and certificate core hashes); timestamps and runtimes are excluded.
Packs are frozen once written: any correction produces a new pack id.
"""

from __future__ import annotations

import datetime as dt
import json
import statistics
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from benchcore.hashing import content_hash, sha256_file

from .baselines import LOCAL_SEARCH_BUDGET, LOCAL_SEARCH_VERSION
from .contracts import InstanceMeta, ShadowTwinsCertificate, ShadowTwinsInstance
from .generator import GeneratorParams, generate_candidate
from .metrics import instance_metrics
from .module import ShadowTwinsModule, attach_verification
from .policy import SELECTION, TIERS, Tier, admission_failures, matches_tier, policy_document
from .solver import certify
from .tokens import PANEL_VERSION, panel_description
from .transforms import geometry_key
from .versions import (
    BENCHMARK_ID,
    EVALUATOR_VERSION,
    GENERATOR_VERSION,
    PARSER_VERSION,
    PROTOCOL_VERSION,
    RULES_VERSION,
    SOLVER_VERSION,
)

PACK_FORMAT = "st-pack-1"
PREFIX = {"development": "st-dev", "practice": "st-prac", "ranked": "st-rank"}


def pack_versions() -> dict[str, str]:
    return {
        "rules": RULES_VERSION, "parser": PARSER_VERSION, "evaluator": EVALUATOR_VERSION,
        "solver": SOLVER_VERSION, "protocol": PROTOCOL_VERSION, "generator": GENERATOR_VERSION,
        "token_panel": PANEL_VERSION, "local_search": LOCAL_SEARCH_VERSION,
        "policy": policy_document()["policy_version"], "pack_format": PACK_FORMAT,
    }


def _measure(args: tuple[int, int, str]) -> dict[str, Any] | None:
    seed, budget, split = args
    inst = generate_candidate(seed, GeneratorParams(budget=budget, split=split, id_prefix=PREFIX[split]))
    if inst is None:
        return {"seed": seed, "status": "structurally_invalid"}
    cert = certify(inst)
    if cert.core.v_star == 0:
        return {"seed": seed, "status": "zero_optimum", "certify_ms": cert.run.runtime_ms}
    m = instance_metrics(inst, cert, with_tokens=True)
    return {
        "seed": seed, "status": "measured", "metrics": m,
        "instance": inst.model_dump(mode="json"), "certificate": cert.model_dump(mode="json"),
        "geometry_key": geometry_key(inst.occupancy_mask, inst.entrance_indices),
    }


def scan_tier(split: str, tier: Tier, target: int, used: set[str], ex: ProcessPoolExecutor,
              chunk: int = 96) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Deterministic selection: results are consumed strictly in seed order."""
    base = SELECTION.seed_bases[split] + SELECTION.tier_offsets[tier.id]
    stats: Counter[str] = Counter()
    accepted: list[dict[str, Any]] = []
    k = 0
    while len(accepted) < target:
        if k >= SELECTION.max_candidates_per_tier:
            raise RuntimeError(f"{split}/{tier.id}: fewer than {target} admitted within "
                               f"{SELECTION.max_candidates_per_tier} candidates")
        jobs = [(base + k + j, tier.budget, split) for j in range(chunk)]
        k += chunk
        for res in ex.map(_measure, jobs):
            if len(accepted) >= target:
                break
            assert res is not None
            stats["examined"] += 1
            if res["status"] != "measured":
                stats[res["status"]] += 1
                continue
            m = res["metrics"]
            fails = admission_failures(m)
            for f in fails:
                stats[f"reject:{f}"] += 1
            if fails:
                stats["not_admitted"] += 1
                continue
            if not matches_tier(m, tier):
                stats["tier_rule_mismatch"] += 1
                continue
            if res["geometry_key"] in used:
                stats["duplicate_geometry"] += 1
                continue
            used.add(res["geometry_key"])
            stats["accepted"] += 1
            res["tier"] = tier.id
            accepted.append(res)
    stats["last_seed_examined_offset"] = k
    return accepted, dict(stats)


def _finalize_instance(res: dict[str, Any], split: str) -> tuple[ShadowTwinsInstance, ShadowTwinsCertificate]:
    inst = ShadowTwinsInstance.model_validate(res["instance"])
    meta = InstanceMeta(split=split, tier=res["tier"], generator_version=GENERATOR_VERSION,  # type: ignore[arg-type]
                        seed=res["seed"])
    inst = inst.model_copy(update={"meta": meta})
    return inst, ShadowTwinsCertificate.model_validate(res["certificate"])


def _verify(args: tuple[dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    inst_doc, cert_doc = args
    module = ShadowTwinsModule()
    inst = ShadowTwinsInstance.model_validate(inst_doc)
    cert = ShadowTwinsCertificate.model_validate(cert_doc)
    report = module.independently_verify(inst, cert)
    return attach_verification(cert, report).model_dump(mode="json")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def baseline_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Baseline scores aggregated like official scores: mean within tier, tiers weighted equally."""
    keys = {
        "noop": lambda m: 0.0,
        "random_legal_expected": lambda m: m["random_legal_expected_score"],
        "random_candidate_expected": lambda m: m["random_candidate_expected_score"],
        "local_search": lambda m: m["local_search_score"],
        "optimum": lambda m: 100.0,
    }
    tiers = sorted({r["tier"] for r in rows})
    out: dict[str, Any] = {"per_tier": {}, "pack": {}}
    for name, fn in keys.items():
        tier_means = {}
        for t in tiers:
            vals = [fn(r["metrics"]) for r in rows if r["tier"] == t]
            tier_means[t] = statistics.fmean(vals)
            out["per_tier"].setdefault(t, {})[name] = tier_means[t]
        out["pack"][name] = statistics.fmean(tier_means.values())
    out["local_search"] = {"version": LOCAL_SEARCH_VERSION, "evaluation_budget": LOCAL_SEARCH_BUDGET}
    return out


def build_pack(pack_id: str, split: str, out_root: Path, used: set[str], jobs: int = 8,
               per_tier: int | None = None) -> dict[str, Any]:
    target = per_tier if per_tier is not None else SELECTION.per_tier[split]
    selected: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    with ProcessPoolExecutor(jobs) as ex:
        for tier in TIERS:
            acc, st = scan_tier(split, tier, target, used, ex)
            selected += acc
            stats[tier.id] = st
        pairs = [_finalize_instance(r, split) for r in selected]
        verified = list(ex.map(_verify, [(i.model_dump(mode="json"), c.model_dump(mode="json"))
                                        for i, c in pairs]))
    out = out_root / pack_id
    items = []
    metrics_rows = []
    token_rows = []
    for order, ((inst, _), cert_doc, res) in enumerate(zip(pairs, verified, selected, strict=True)):
        cert = ShadowTwinsCertificate.model_validate(cert_doc)
        if cert.independent_verification.status != "verified":
            raise RuntimeError(f"{inst.instance_id}: independent verification failed: "
                               f"{cert.independent_verification.mismatches}")
        ip = out / "instances" / f"{inst.instance_id}.json"
        cp = out / "certificates" / f"{inst.instance_id}.json"
        _write(ip, inst.model_dump(mode="json"))
        _write(cp, cert.model_dump(mode="json"))
        m = res["metrics"]
        items.append({
            "order": order,
            "instance_id": inst.instance_id,
            "tier": res["tier"],
            "seed": res["seed"],
            "content_hash": inst.content_hash,
            "certificate_core_hash": cert.core_hash,
            "v_star": cert.core.v_star,
            "tokens_max": m["tokens_max"],
            "verified": True,
            "instance": f"instances/{inst.instance_id}.json",
            "instance_file_hash": sha256_file(str(ip)),
            "certificate": f"certificates/{inst.instance_id}.json",
            "certificate_file_hash": sha256_file(str(cp)),
        })
        metrics_rows.append({"instance_id": inst.instance_id, "tier": res["tier"], "metrics": m})
        token_rows.append({"instance_id": inst.instance_id, "counts": m["tokens"], "max": m["tokens_max"]})

    versions = pack_versions()
    policy = policy_document()
    identity = {
        "pack_id": pack_id, "split": split, "benchmark_id": BENCHMARK_ID, "versions": versions,
        "policy_hash": policy["policy_hash"],
        "items": [{k: it[k] for k in ("order", "instance_id", "tier", "content_hash",
                                      "certificate_core_hash", "v_star")} for it in items],
    }
    per_tok_max: dict[str, int] = {}
    for row in token_rows:
        for k, v in row["counts"].items():
            per_tok_max[k] = max(per_tok_max.get(k, 0), v)
    manifest = {
        "pack_id": pack_id,
        "pack_format": PACK_FORMAT,
        "split": split,
        "benchmark_id": BENCHMARK_ID,
        "frozen": True,
        "ranked": split == "ranked",
        "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "versions": versions,
        "policy_hash": policy["policy_hash"],
        "tiers": [{"id": t.id, "name": t.name, "budget": t.budget, "rule": t.rule,
                   "count": sum(1 for it in items if it["tier"] == t.id)} for t in TIERS],
        "selection_stats": stats,
        "token_report": {"panel_version": PANEL_VERSION, "ceiling": policy["admission"]["max_tokens"],
                         "max": max(r["max"] for r in token_rows), "per_tokenizer_max": per_tok_max},
        "items": items,
        "pack_hash": content_hash(identity),
    }
    _write(out / "reports" / "metrics.json", metrics_rows)
    _write(out / "reports" / "tokens.json", {"panel": panel_description(), "items": token_rows})
    _write(out / "reports" / "baselines.json", baseline_summary(
        [{"tier": r["tier"], "metrics": r["metrics"]} for r in metrics_rows]))
    _write(out / "policy.json", policy)
    _write(out / "manifest.json", manifest)
    return manifest


def development_scan(n_per_tier: int, jobs: int = 8) -> list[dict[str, Any]]:
    """Measure *every* candidate in the development seed range (no admission filtering)."""
    rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(jobs) as ex:
        for tier in TIERS:
            base = SELECTION.seed_bases["development"] + SELECTION.tier_offsets[tier.id]
            jobs_ = [(base + k, tier.budget, "development") for k in range(n_per_tier)]
            for res in ex.map(_measure, jobs_, chunksize=8):
                assert res is not None
                row = {"seed": res["seed"], "budget": tier.budget, "status": res["status"]}
                if res["status"] == "measured":
                    m = res["metrics"]
                    row["metrics"] = m
                    row["admission_failures"] = admission_failures(m)
                    row["tier_match"] = matches_tier(m, tier)
                rows.append(row)
    return rows


def used_geometry_keys(pack_dirs: list[Path]) -> set[str]:
    keys: set[str] = set()
    for d in pack_dirs:
        manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        for it in manifest["items"]:
            inst = ShadowTwinsInstance.model_validate_json((d / it["instance"]).read_text(encoding="utf-8"))
            keys.add(geometry_key(inst.occupancy_mask, inst.entrance_indices))
    return keys


def load_pack(pack_dir: Path) -> tuple[dict[str, Any], list[tuple[ShadowTwinsInstance, ShadowTwinsCertificate, dict[str, Any]]]]:
    """Load and integrity-check a pack (file hashes, content hashes, verification status)."""
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    out = []
    for it in manifest["items"]:
        ip, cp = pack_dir / it["instance"], pack_dir / it["certificate"]
        if sha256_file(str(ip)) != it["instance_file_hash"]:
            raise ValueError(f"{ip}: file hash differs from manifest")
        if sha256_file(str(cp)) != it["certificate_file_hash"]:
            raise ValueError(f"{cp}: file hash differs from manifest")
        inst = ShadowTwinsInstance.model_validate_json(ip.read_text(encoding="utf-8"))
        cert = ShadowTwinsCertificate.model_validate_json(cp.read_text(encoding="utf-8"))
        if inst.content_hash != it["content_hash"] or cert.core_hash != it["certificate_core_hash"]:
            raise ValueError(f"{it['instance_id']}: identity hash differs from manifest")
        if cert.core.instance_hash != inst.content_hash:
            raise ValueError(f"{it['instance_id']}: certificate belongs to another instance")
        out.append((inst, cert, it))
    return manifest, out
