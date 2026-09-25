"""Exports (JSON with full geometry and provenance; CSV analysis table) and offline re-evaluation.

Neither export can contain credentials: the database never stores them, and request records are
provider-neutral bodies without headers.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from typing import Any

from benchcore.aggregate import ScoredItem, aggregate
from benchcore.contracts import CompletionMeta, FinishReason

from . import runs
from .context import AppContext
from .db import jload, now

EXPORT_VERSION = "export-1.0.0"

CSV_COLUMNS = [
    "run_id", "model_id", "endpoint", "profile_id", "track", "suite_version", "pack_id", "instance_id",
    "tier", "repetition", "job_state", "attempts", "valid", "category", "score", "raw_objective",
    "max_objective", "evaluator_version", "certificate_hash", "prompt_tokens", "completion_tokens",
    "reasoning_tokens", "cost_usd", "cost_source", "latency_ms", "provider_name", "response_model",
    "finish_reason",
]


def _last_response(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM attempts WHERE job_id=? AND state='response' ORDER BY number DESC LIMIT 1",
                        (job_id,)).fetchone()


def export_json(ctx: AppContext, conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    s = runs.summary(conn, run_id)
    pack = conn.execute("SELECT manifest_json FROM packs WHERE pack_id=?", (s["pack_id"],)).fetchone()
    manifest = jload(pack["manifest_json"])
    items = []
    for job in conn.execute("SELECT * FROM jobs WHERE run_id=? ORDER BY ord", (run_id,)).fetchall():
        _, inst, cert, _row = ctx.load_item(conn, job["instance_id"])
        attempts = []
        for a in conn.execute("SELECT * FROM attempts WHERE job_id=? ORDER BY number", (job["job_id"],)):
            d = dict(a)
            d["request"] = jload(d.pop("request_json"))
            d["response"] = jload(d.pop("response_json"))
            attempts.append(d)
        ev = conn.execute("SELECT envelope_json FROM evaluations WHERE evaluation_id=?",
                          (job["evaluation_id"],)).fetchone()
        items.append({
            "job": {k: job[k] for k in ("job_id", "instance_id", "tier", "repetition", "ord", "state",
                                        "attempts", "last_error")},
            "instance": inst.model_dump(mode="json"),
            "certificate": cert.model_dump(mode="json"),
            "attempts": attempts,
            "evaluation": jload(ev["envelope_json"]) if ev else None,
        })
    return {
        "export_version": EXPORT_VERSION, "generated_at": now(), "run": s,
        "pack": {k: manifest.get(k) for k in ("pack_id", "pack_hash", "policy_hash", "split", "versions", "tiers")},
        "items": items,
    }


def export_csv(conn: sqlite3.Connection, run_id: str) -> str:
    s = runs.summary(conn, run_id)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, lineterminator="\n")
    w.writeheader()
    for job in conn.execute("SELECT * FROM jobs WHERE run_id=? ORDER BY ord", (run_id,)).fetchall():
        ev = conn.execute("SELECT * FROM evaluations WHERE evaluation_id=?", (job["evaluation_id"],)).fetchone()
        a = _last_response(conn, job["job_id"])
        cost = conn.execute("SELECT SUM(cost_usd), GROUP_CONCAT(DISTINCT cost_source) FROM attempts WHERE job_id=?",
                            (job["job_id"],)).fetchone()
        w.writerow({
            "run_id": run_id, "model_id": s["model_id"], "endpoint": s["endpoint"], "profile_id": s["profile_id"],
            "track": s["track"], "suite_version": s["suite_version"], "pack_id": s["pack_id"],
            "instance_id": job["instance_id"], "tier": job["tier"], "repetition": job["repetition"],
            "job_state": job["state"], "attempts": job["attempts"],
            "valid": "" if ev is None else int(ev["valid"]), "category": "" if ev is None else (ev["category"] or ""),
            "score": "" if ev is None else repr(ev["score"]),
            "raw_objective": "" if ev is None or ev["raw_objective"] is None else ev["raw_objective"],
            "max_objective": "" if ev is None else ev["max_objective"],
            "evaluator_version": "" if ev is None else ev["evaluator_version"],
            "certificate_hash": "" if ev is None else ev["certificate_hash"],
            "prompt_tokens": a["prompt_tokens"] if a else "", "completion_tokens": a["completion_tokens"] if a else "",
            "reasoning_tokens": a["reasoning_tokens"] if a else "",
            "cost_usd": "" if cost[0] is None else repr(cost[0]), "cost_source": cost[1] or "",
            "latency_ms": a["latency_ms"] if a else "", "provider_name": a["provider_name"] if a else "",
            "response_model": a["response_model"] if a else "", "finish_reason": a["finish_reason"] if a else "",
        })
    return buf.getvalue()


def reevaluate(ctx: AppContext, conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    """Re-score every stored raw response with the current evaluator and compare."""
    mismatches: list[dict[str, Any]] = []
    items: list[ScoredItem] = []
    checked = 0
    for job in conn.execute("SELECT * FROM jobs WHERE run_id=? ORDER BY ord", (run_id,)).fetchall():
        if job["state"] != "completed":
            items.append(ScoredItem(job["instance_id"], job["tier"], job["repetition"], job["state"]))
            continue
        ev = conn.execute("SELECT * FROM evaluations WHERE evaluation_id=?", (job["evaluation_id"],)).fetchone()
        a = conn.execute("SELECT * FROM attempts WHERE attempt_id=?", (ev["attempt_id"],)).fetchone()
        module, inst, cert, row = ctx.load_item(conn, job["instance_id"])
        try:
            fr = FinishReason(a["finish_reason"]) if a["finish_reason"] else FinishReason.UNKNOWN
        except ValueError:
            fr = FinishReason.UNKNOWN
        env = module.evaluate(inst, cert, a["content"] or "",
                              CompletionMeta(finish_reason=fr, native_finish_reason=a["native_finish_reason"],
                                             refusal=a["refusal"]))
        checked += 1
        stored = (bool(ev["valid"]), ev["category"], ev["score"], ev["raw_objective"])
        fresh = (env.valid, env.category, env.score, env.raw_objective)
        if stored != fresh or ev["certificate_hash"] != row["core_hash"]:
            mismatches.append({"job_id": job["job_id"], "instance_id": job["instance_id"],
                               "stored": stored, "recomputed": fresh})
        items.append(ScoredItem(job["instance_id"], job["tier"], job["repetition"], "completed", env.score,
                                env.valid, env.raw_objective == env.max_objective if env.valid else False,
                                env.category))
    fresh_agg = aggregate(items)
    stored_agg = runs.summary(conn, run_id)["scores"]
    agg_match = (fresh_agg["overall"] == stored_agg["overall"]
                 and fresh_agg["provisional_overall"] == stored_agg["provisional_overall"]
                 and fresh_agg["tiers"] == stored_agg["tiers"])
    return {"run_id": run_id, "checked": checked, "mismatches": mismatches,
            "aggregate_matches": agg_match, "recomputed": fresh_agg, "stored": stored_agg}
