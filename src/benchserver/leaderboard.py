"""Leaderboard listing policy and model detail.

Policy (``lb-1.0.0``): for each (model, pinned endpoint, profile and its version, track, pack hash,
suite version)
list the **latest** completed run that is leaderboard-eligible — ranked, not mock, completed with
every item evaluated, and with provider consistency not contradicted. Never the highest historical
run. All run history stays accessible through model detail. With suite-1 (one benchmark), the
overall score equals the Shadow Twins score.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from benchcore.contracts import SUITE_BENCHMARKS, SUITE_VERSION

from . import runs
from .db import jload

LISTING_POLICY = "lb-1.0.0"


def _profile_version(profile_json: str | None) -> str:
    return str((jload(profile_json) or {}).get("version", ""))


def _group_key(r: sqlite3.Row) -> tuple[str, ...]:
    # The profile version is part of the key: runs under different output budgets are not comparable.
    return (r["model_id"], r["endpoint"] or "", r["profile_id"], _profile_version(r["profile_json"]), r["track"],
            r["pack_hash"], r["suite_version"])


def leaderboard(conn: sqlite3.Connection, track: str = "standard", profile_id: str | None = None) -> dict[str, Any]:
    q = ("SELECT * FROM runs WHERE ranked=1 AND is_mock=0 AND state='completed' AND track=?"
         + (" AND profile_id=?" if profile_id else "") + " ORDER BY completed_at DESC")
    args = (track, profile_id) if profile_id else (track,)
    chosen: dict[tuple[str, ...], dict[str, Any]] = {}
    history: dict[tuple[str, ...], int] = {}
    for r in conn.execute(q, args).fetchall():
        key = _group_key(r)
        history[key] = history.get(key, 0) + 1
        if key in chosen:
            continue
        s = runs.summary(conn, r["run_id"])
        if not s["leaderboard_eligible"]:
            continue
        chosen[key] = s
    rows = []
    for key, s in chosen.items():
        sc = s["scores"]
        meta = s["model_meta"] or {}
        rows.append({
            "model_id": s["model_id"], "model_name": (meta.get("model") or {}).get("name", s["model_id"]),
            "endpoint": s["endpoint"],
            "provider_name": (meta.get("endpoint") or {}).get("provider_name") or ("Groq" if s["provider"] == "groq" else None),
            "profile_id": s["profile_id"], "track": s["track"],
            "overall": sc["overall"], "shadow_twins": sc["overall"],
            "tiers": sc["tiers"], "interval_95": sc["interval_95"],
            "valid_rate": sc["valid_rate"], "conditional_quality": sc["conditional_quality"],
            "optimal_rate": sc["optimal_rate"], "completed": sc["completed"], "scheduled": sc["scheduled"],
            "cost_usd": s["cost"]["spent_usd"], "latency_ms": s["latency_ms"]["mean"],
            "evaluated_at": s["completed_at"], "suite_version": s["suite_version"],
            "pack_id": s["pack_id"], "pack_hash": s["pack_hash"],
            "versions": {**s["versions"], "profile": str((s["profile"] or {}).get("version", ""))},
            "run_id": s["run_id"], "runs_in_group": history[key],
        })
    rows.sort(key=lambda x: (-(x["overall"] or 0.0), x["model_id"]))
    rank = 0
    prev: float | None = None
    for i, row in enumerate(rows, start=1):
        if row["overall"] != prev:
            rank, prev = i, row["overall"]
        row["rank"] = rank
    return {
        "listing_policy": LISTING_POLICY, "track": track, "profile_id": profile_id,
        "suite": {"version": SUITE_VERSION, "benchmarks": list(SUITE_BENCHMARKS),
                  "note": "Suite 1 contains one benchmark; overall equals the Shadow Twins score."},
        "rows": rows,
    }


def model_detail(conn: sqlite3.Connection, model_id: str) -> dict[str, Any]:
    all_runs = runs.list_runs(conn, model_id=model_id, limit=500)
    if not all_runs:
        return {"model_id": model_id, "runs": [], "latest_eligible": [], "categories": {}}
    latest: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    cats: dict[str, int] = {}
    for s in all_runs:
        k = (s["endpoint"] or "", s["profile_id"], str((s["profile"] or {}).get("version", "")), s["track"])
        if s["leaderboard_eligible"] and k not in latest:
            latest[k] = s
        for c, n in s["scores"]["categories"].items():
            cats[c] = cats.get(c, 0) + n
    usage = conn.execute(
        "SELECT COUNT(*) n, AVG(prompt_tokens) p, AVG(completion_tokens) c, AVG(reasoning_tokens) r, "
        "AVG(latency_ms) l, SUM(cost_usd) cost FROM attempts a JOIN runs r USING(run_id) "
        "WHERE r.model_id=? AND a.state='response'", (model_id,)).fetchone()
    scores = [r["score"] for r in conn.execute(
        "SELECT e.score FROM evaluations e JOIN runs r USING(run_id) WHERE r.model_id=? AND r.is_mock=0",
        (model_id,))]
    hist = [0] * 10
    for sc in scores:
        hist[min(9, int(sc // 10))] += 1
    meta = jload(conn.execute("SELECT model_meta_json FROM runs WHERE model_id=? ORDER BY created_at DESC LIMIT 1",
                              (model_id,)).fetchone()["model_meta_json"])
    return {
        "model_id": model_id, "model": (meta or {}).get("model"),
        "latest_eligible": list(latest.values()),
        "runs": [{k: s[k] for k in ("run_id", "created_at", "completed_at", "state", "track", "profile_id",
                                    "endpoint", "ranked", "is_mock", "leaderboard_eligible", "ineligible_reasons",
                                    "fingerprint")} | {"overall": s["scores"]["overall"],
                                                       "provisional_overall": s["scores"]["provisional_overall"],
                                                       "valid_rate": s["scores"]["valid_rate"],
                                                       "optimal_rate": s["scores"]["optimal_rate"],
                                                       "cost_usd": s["cost"]["spent_usd"]} for s in all_runs],
        "categories": cats,
        "score_histogram": {"bins": [f"{10 * i}-{10 * i + 10}" for i in range(10)], "counts": hist},
        "usage": dict(usage) if usage else {},
    }
