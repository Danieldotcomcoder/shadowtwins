"""Run lifecycle: planning, creation, operator controls, state finalization and read models.

Run states: ``active`` → (``paused`` | ``budget_stopped`` | ``cancelling``) → terminal
``completed`` | ``incomplete`` | ``cancelled``. A run is ``completed`` only when every scheduled
job has a completed, evaluated answer; otherwise it ends ``incomplete`` and has no official total.
Browser connections never affect a run: all progress is persisted state.
"""

from __future__ import annotations

import secrets
import sqlite3
import statistics
from typing import Any

from benchcore.aggregate import AGGREGATION_VERSION, ScoredItem, aggregate
from benchcore.contracts import (
    CONTRACTS_VERSION,
    SUITE_VERSION,
    JobState,
    RunMode,
    RunSpec,
    RunState,
)
from benchcore.hashing import content_hash

from . import catalog, costs, events
from .context import AppContext
from .db import jdump, jload, now, tx
from .profiles import PROFILE_BY_ID, compatibility, request_params

MODES: dict[RunMode, dict[str, Any]] = {
    RunMode.QUICK_CHECK: {"split": "practice", "repetitions": 1, "track": "quick_check"},
    RunMode.STANDARD: {"split": "ranked", "repetitions": 1, "track": "standard"},
    RunMode.REPEATED: {"split": "ranked", "repetitions": 3, "track": "repeated"},
}
TERMINAL_RUN_STATES = {RunState.COMPLETED, RunState.INCOMPLETE, RunState.CANCELLED}
OPEN_JOB_STATES = (JobState.QUEUED, JobState.RETRY_WAIT, JobState.LEASED)


class RunError(Exception):
    def __init__(self, status: int, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.detail = detail


def _pack(conn: sqlite3.Connection, split: str, pack_id: str | None) -> sqlite3.Row:
    if pack_id:
        row = conn.execute("SELECT * FROM packs WHERE pack_id=?", (pack_id,)).fetchone()
        if row is None or row["split"] != split:
            raise RunError(400, f"pack {pack_id} is not a loaded {split} pack")
        return row
    row = conn.execute("SELECT * FROM packs WHERE split=? ORDER BY pack_id DESC LIMIT 1", (split,)).fetchone()
    if row is None:
        raise RunError(409, f"no {split} pack is loaded on this server")
    return row


async def plan(ctx: AppContext, conn: sqlite3.Connection, spec: RunSpec, pack_id: str | None = None) -> dict[str, Any]:
    """Validate a run request and estimate its cost without creating anything."""
    mode = MODES[spec.mode]
    provider = ctx.provider_name_for(spec.model_id)
    if provider not in ctx.providers:
        raise RunError(400, f"provider '{provider}' is not enabled on this server")
    found = catalog.find_model(conn, provider, spec.model_id)
    if found is None:
        await catalog.catalog(ctx, conn, force=True)
        found = catalog.find_model(conn, provider, spec.model_id)
    if found is None:
        raise RunError(404, f"model {spec.model_id} is not in the {provider} catalog")
    model, snapshot_id = found
    profile = PROFILE_BY_ID.get(spec.profile_id)
    if profile is None:
        raise RunError(400, f"unknown profile {spec.profile_id}")
    pack = _pack(conn, mode["split"], pack_id)
    items = conn.execute("SELECT instance_id, tier, ord, tokens_max FROM instances WHERE pack_id=? ORDER BY ord",
                         (pack["pack_id"],)).fetchall()
    endpoint = None
    endpoint_error = None
    if spec.provider:
        eps, endpoint_error = await catalog.endpoints(ctx, conn, spec.model_id)
        endpoint = next((e for e in eps if e.slug == spec.provider), None)
        if endpoint is None:
            raise RunError(400, f"endpoint '{spec.provider}' is not listed for {spec.model_id}",
                           {"available": [e.slug for e in eps], "error": endpoint_error})
    pricing = endpoint.pricing if endpoint else model.pricing
    prompt_max = max((r["tokens_max"] or 800) for r in items)
    compat = compatibility(model, profile, costs.prompt_estimate(prompt_max), endpoint)
    tokens = [r["tokens_max"] for r in items] * mode["repetitions"]
    est = costs.estimate(pricing, tokens, profile.max_tokens)

    blocking: list[str] = []
    if not compat["compatible"]:
        blocking += [f"profile incompatible: {p}" for p in compat["problems"]]
    if not est["pricing_known"] and not spec.allow_unknown_pricing:
        blocking.append("model pricing is unknown; an explicit unranked override is required")
    if provider == "openrouter" and not ctx.settings.openrouter_configured:
        blocking.append("OPENROUTER_API_KEY is not configured on the server")
    if est["max_per_call_usd"] is not None and spec.spend_limit_usd < est["max_per_call_usd"]:
        blocking.append(f"spend limit ${spec.spend_limit_usd:.4f} is below one call's reservation "
                        f"${est['max_per_call_usd']:.4f}")

    not_ranked: list[str] = []
    if not pack["ranked"]:
        not_ranked.append("quick check uses unranked practice instances")
    if model.is_mock:
        not_ranked.append("mock provider (test double)")
    if endpoint is None:
        not_ranked.append("no pinned provider endpoint (fallbacks cannot be disabled)")
    if not est["pricing_known"]:
        not_ranked.append("pricing unknown (unranked override)")
    return {
        "model": model.to_dict(), "snapshot_id": snapshot_id, "provider": provider,
        "endpoint": endpoint.to_dict() if endpoint else None, "endpoint_error": endpoint_error,
        "profile": profile.to_dict(), "compatibility": compat,
        "pack": {"pack_id": pack["pack_id"], "pack_hash": pack["pack_hash"], "split": pack["split"],
                 "ranked": bool(pack["ranked"]), "instances": len(items)},
        "mode": spec.mode.value, "track": mode["track"], "repetitions": mode["repetitions"],
        "estimate": est, "pricing": pricing,
        "ranked": not not_ranked and not blocking, "not_ranked_reasons": not_ranked,
        "blocking": blocking,
    }


async def create(ctx: AppContext, conn: sqlite3.Connection, spec: RunSpec, pack_id: str | None = None) -> str:
    p = await plan(ctx, conn, spec, pack_id)
    if p["blocking"]:
        raise RunError(400, "run cannot start: " + "; ".join(p["blocking"]), p)
    model = catalog.model_from_dict(p["model"])
    endpoint = catalog.endpoint_from_dict(p["endpoint"]) if p["endpoint"] else None
    profile = PROFILE_BY_ID[spec.profile_id]
    params, settings_record = request_params(model, profile, endpoint)
    pack = conn.execute("SELECT * FROM packs WHERE pack_id=?", (p["pack"]["pack_id"],)).fetchone()
    module = ctx.module(pack["benchmark_id"])
    versions = {**module.metadata().versions, "suite": SUITE_VERSION, "contracts": CONTRACTS_VERSION,
                "aggregation": AGGREGATION_VERSION}
    template = {"model_id": spec.model_id, "params": params, "endpoint": spec.provider,
                "allow_fallbacks": spec.provider is None, "settings": settings_record}
    fingerprint = content_hash({
        "provider": p["provider"], "model_id": spec.model_id, "endpoint": spec.provider,
        "profile": profile.to_dict(), "params": params, "pack_hash": pack["pack_hash"],
        "track": p["track"], "repetitions": p["repetitions"], "versions": versions,
    })
    run_id = "run_" + now()[:19].replace("-", "").replace(":", "").replace("T", "_") + "_" + secrets.token_hex(3)
    ts = now()
    items = conn.execute("SELECT instance_id, tier, ord FROM instances WHERE pack_id=? ORDER BY ord",
                         (pack["pack_id"],)).fetchall()
    with tx(conn):
        conn.execute(
            "INSERT INTO runs(run_id, created_at, updated_at, provider, model_id, endpoint, profile_id, "
            "profile_json, mode, track, pack_id, pack_hash, repetitions, ranked, ranked_reasons_json, is_mock, "
            "suite_version, versions_json, request_template_json, fingerprint, catalog_snapshot_id, "
            "model_meta_json, state, spend_limit_usd, concurrency, allow_unknown_pricing, pricing_json, "
            "pricing_known, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, ts, ts, p["provider"], spec.model_id, spec.provider, profile.id, jdump(profile.to_dict()),
             spec.mode.value, p["track"], pack["pack_id"], pack["pack_hash"], p["repetitions"],
             int(p["ranked"]), jdump(p["not_ranked_reasons"]), int(model.is_mock), SUITE_VERSION,
             jdump(versions), jdump(template), fingerprint, p["snapshot_id"],
             jdump({"model": p["model"], "endpoint": p["endpoint"], "compatibility": p["compatibility"],
                    "estimate": p["estimate"]}),
             RunState.ACTIVE.value, spec.spend_limit_usd, spec.concurrency, int(spec.allow_unknown_pricing),
             jdump(p["pricing"]), int(p["estimate"]["pricing_known"]), spec.note))
        n = len(items)
        for rep in range(1, p["repetitions"] + 1):
            for it in items:
                conn.execute(
                    "INSERT INTO jobs(run_id, instance_id, tier, repetition, ord, state, updated_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (run_id, it["instance_id"], it["tier"], rep, (rep - 1) * n + it["ord"], JobState.QUEUED.value, ts))
        catalog.push_recent(conn, spec.model_id)
        events.emit(conn, run_id, "run_created", {"model_id": spec.model_id, "jobs": n * p["repetitions"],
                                                  "ranked": p["ranked"], "track": p["track"]})
    return run_id


# --- controls -------------------------------------------------------------------------------

def _get_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        raise RunError(404, f"run {run_id} not found")
    return row


def set_state(conn: sqlite3.Connection, run_id: str, state: RunState, reason: str | None = None) -> None:
    conn.execute("UPDATE runs SET state=?, state_reason=?, updated_at=?, completed_at=CASE WHEN ? IN "
                 "('completed','incomplete','cancelled') THEN ? ELSE completed_at END WHERE run_id=?",
                 (state.value, reason, now(), state.value, now(), run_id))
    events.emit(conn, run_id, "run_state", {"state": state.value, "reason": reason})


def control(conn: sqlite3.Connection, run_id: str, action: str, value: float | None = None) -> dict[str, Any]:
    with tx(conn):
        run = _get_run(conn, run_id)
        state = RunState(run["state"])
        if action == "pause":
            if state not in (RunState.ACTIVE, RunState.BUDGET_STOPPED):
                raise RunError(409, f"cannot pause a run that is {state.value}")
            set_state(conn, run_id, RunState.PAUSED, "paused by operator; in-flight requests will settle")
        elif action == "resume":
            if state not in (RunState.PAUSED, RunState.BUDGET_STOPPED):
                raise RunError(409, f"cannot resume a run that is {state.value}")
            set_state(conn, run_id, RunState.ACTIVE, "resumed by operator")
        elif action == "cancel":
            if state in TERMINAL_RUN_STATES or state == RunState.CANCELLING:
                raise RunError(409, f"cannot cancel a run that is {state.value}")
            cur = conn.execute("UPDATE jobs SET state='cancelled', updated_at=? WHERE run_id=? AND state IN "
                               "('queued','retry_wait')", (now(), run_id))
            set_state(conn, run_id, RunState.CANCELLING,
                      f"cancelled by operator; {cur.rowcount} unsent jobs cancelled, in-flight requests settle")
        elif action in ("rerun_uncertain", "retry_failed"):
            src = "uncertain" if action == "rerun_uncertain" else "failed"
            if state in (RunState.CANCELLED, RunState.CANCELLING):
                raise RunError(409, "run was cancelled")
            ids = [r[0] for r in conn.execute("SELECT job_id FROM jobs WHERE run_id=? AND state=?", (run_id, src))]
            if not ids:
                raise RunError(409, f"no {src} jobs to requeue")
            conn.execute(f"UPDATE jobs SET state='queued', not_before=NULL, updated_at=? WHERE run_id=? AND state='{src}'",
                         (now(), run_id))
            events.emit(conn, run_id, "jobs_requeued", {
                "from": src, "job_ids": ids,
                "note": "explicit rerun: a previous request may already have been charged" if src == "uncertain" else
                        "explicit retry of final infrastructure failures"})
            set_state(conn, run_id, RunState.ACTIVE, f"{len(ids)} {src} jobs requeued by operator")
        elif action == "set_spend_limit":
            if value is None or value <= 0:
                raise RunError(400, "spend limit must be positive")
            if value < run["spent_usd"] + run["reserved_usd"]:
                raise RunError(400, "limit is below money already spent or reserved")
            conn.execute("UPDATE runs SET spend_limit_usd=?, updated_at=? WHERE run_id=?", (value, now(), run_id))
            events.emit(conn, run_id, "spend_limit", {"spend_limit_usd": value})
        else:
            raise RunError(400, f"unknown action {action}")
    finalize(conn, run_id)
    return summary(conn, run_id)


def finalize(conn: sqlite3.Connection, run_id: str) -> None:
    """Move a run to a terminal state once nothing remains to dispatch or settle."""
    with tx(conn):
        run = _get_run(conn, run_id)
        state = RunState(run["state"])
        if state in TERMINAL_RUN_STATES:
            return
        counts = {r["state"]: r["n"] for r in conn.execute(
            "SELECT state, COUNT(*) n FROM jobs WHERE run_id=? GROUP BY state", (run_id,))}
        leased = counts.get("leased", 0)
        pending = counts.get("queued", 0) + counts.get("retry_wait", 0)
        if state == RunState.CANCELLING and leased == 0:
            set_state(conn, run_id, RunState.CANCELLED, "all in-flight requests settled")
        elif state == RunState.ACTIVE and leased == 0 and pending == 0:
            total = sum(counts.values())
            if counts.get("completed", 0) == total:
                set_state(conn, run_id, RunState.COMPLETED, None)
            else:
                open_ = {k: v for k, v in counts.items() if k != "completed"}
                set_state(conn, run_id, RunState.INCOMPLETE,
                          "unresolved jobs: " + ", ".join(f"{v} {k}" for k, v in sorted(open_.items())))


# --- read models ----------------------------------------------------------------------------

def scored_items(conn: sqlite3.Connection, run_id: str) -> list[ScoredItem]:
    rows = conn.execute(
        "SELECT j.instance_id, j.tier, j.repetition, j.state, e.score, e.valid, e.category, e.raw_objective, "
        "e.max_objective FROM jobs j LEFT JOIN evaluations e ON e.evaluation_id = j.evaluation_id "
        "WHERE j.run_id=? ORDER BY j.ord", (run_id,)).fetchall()
    return [ScoredItem(
        instance_id=r["instance_id"], tier=r["tier"], repetition=r["repetition"], state=r["state"],
        score=r["score"], valid=bool(r["valid"]) if r["valid"] is not None else None,
        optimal=(r["raw_objective"] == r["max_objective"]) if r["valid"] else (False if r["valid"] is not None else None),
        category=r["category"]) for r in rows]


def observed_consistency(conn: sqlite3.Connection, run: sqlite3.Row) -> dict[str, Any]:
    """Compare requested model/endpoint with what the provider reported on every response."""
    rows = conn.execute("SELECT DISTINCT provider_name, response_model FROM attempts WHERE run_id=? "
                        "AND state='response'", (run["run_id"],)).fetchall()
    meta = jload(run["model_meta_json"]) or {}
    ep = meta.get("endpoint") or {}
    providers = sorted({r["provider_name"] for r in rows if r["provider_name"]})
    models = sorted({r["response_model"] for r in rows if r["response_model"]})
    provider_ok: bool | None = None
    if ep and providers:
        provider_ok = all(p.lower() == (ep.get("provider_name") or "").lower() for p in providers)
    unreported = any(r["provider_name"] is None for r in rows)
    base = run["model_id"].split(":")[0]
    model_ok = all(m == run["model_id"] or m.startswith(base) for m in models) if models else None
    return {"observed_providers": providers, "observed_models": models,
            "provider_matches_pin": provider_ok, "model_matches_request": model_ok,
            "provider_unreported_on_some_responses": unreported}


def summary(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    run = _get_run(conn, run_id)
    items = scored_items(conn, run_id)
    agg = aggregate(items)
    lat = [r[0] for r in conn.execute("SELECT latency_ms FROM attempts WHERE run_id=? AND state='response' "
                                      "AND latency_ms IS NOT NULL", (run_id,))]
    tok = conn.execute("SELECT COALESCE(SUM(prompt_tokens),0) p, COALESCE(SUM(completion_tokens),0) c, "
                       "COALESCE(SUM(reasoning_tokens),0) r, COUNT(*) n, "
                       "SUM(CASE WHEN cost_source='estimated' THEN 1 ELSE 0 END) est, "
                       "SUM(CASE WHEN cost_source='reserved_uncertain' THEN 1 ELSE 0 END) unc "
                       "FROM attempts WHERE run_id=?", (run_id,)).fetchone()
    consistency = observed_consistency(conn, run)
    eligible_reasons = list(jload(run["ranked_reasons_json"]) or [])
    if run["state"] != RunState.COMPLETED.value:
        eligible_reasons.append(f"run is {run['state']}")
    if consistency["provider_matches_pin"] is False:
        eligible_reasons.append("observed provider differs from the pinned endpoint")
    return {
        "run_id": run_id,
        "created_at": run["created_at"], "updated_at": run["updated_at"], "completed_at": run["completed_at"],
        "state": run["state"], "state_reason": run["state_reason"],
        "provider": run["provider"], "model_id": run["model_id"], "endpoint": run["endpoint"],
        "profile_id": run["profile_id"], "profile": jload(run["profile_json"]),
        "mode": run["mode"], "track": run["track"], "pack_id": run["pack_id"], "pack_hash": run["pack_hash"],
        "repetitions": run["repetitions"], "is_mock": bool(run["is_mock"]),
        "ranked": bool(run["ranked"]), "not_ranked_reasons": jload(run["ranked_reasons_json"]),
        "leaderboard_eligible": bool(run["ranked"]) and not eligible_reasons,
        "ineligible_reasons": eligible_reasons,
        "suite_version": run["suite_version"], "versions": jload(run["versions_json"]),
        "fingerprint": run["fingerprint"], "request": jload(run["request_template_json"]),
        "model_meta": jload(run["model_meta_json"]),
        "consistency": consistency,
        "cost": {"spend_limit_usd": run["spend_limit_usd"], "spent_usd": run["spent_usd"],
                 "reserved_usd": run["reserved_usd"], "pricing": jload(run["pricing_json"]),
                 "pricing_known": bool(run["pricing_known"]),
                 "estimated_cost_attempts": tok["est"] or 0, "uncertain_cost_attempts": tok["unc"] or 0},
        "usage": {"prompt_tokens": tok["p"], "completion_tokens": tok["c"], "reasoning_tokens": tok["r"],
                  "attempts": tok["n"]},
        "latency_ms": {"mean": statistics.fmean(lat) if lat else None,
                       "median": statistics.median(lat) if lat else None, "n": len(lat)},
        "concurrency": run["concurrency"],
        "scores": agg,
        "last_event_id": events.last_id(conn, run_id),
    }


def list_runs(conn: sqlite3.Connection, model_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    q = "SELECT run_id FROM runs"
    args: tuple[Any, ...] = ()
    if model_id:
        q += " WHERE model_id=?"
        args = (model_id,)
    q += " ORDER BY created_at DESC LIMIT ?"
    return [summary(conn, r["run_id"]) for r in conn.execute(q, (*args, limit)).fetchall()]


def items(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    _get_run(conn, run_id)
    rows = conn.execute(
        "SELECT j.job_id, j.instance_id, j.tier, j.repetition, j.ord, j.state, j.attempts, j.last_error, "
        "e.valid, e.category, e.score, e.raw_objective, e.max_objective, "
        "(SELECT SUM(cost_usd) FROM attempts a WHERE a.job_id=j.job_id) cost_usd, "
        "(SELECT latency_ms FROM attempts a WHERE a.job_id=j.job_id AND a.state='response' "
        " ORDER BY number DESC LIMIT 1) latency_ms "
        "FROM jobs j LEFT JOIN evaluations e ON e.evaluation_id=j.evaluation_id WHERE j.run_id=? ORDER BY j.ord",
        (run_id,)).fetchall()
    return [dict(r) | {"valid": None if r["valid"] is None else bool(r["valid"])} for r in rows]


def job_detail(ctx: AppContext, conn: sqlite3.Connection, run_id: str, job_id: int) -> dict[str, Any]:
    job = conn.execute("SELECT * FROM jobs WHERE run_id=? AND job_id=?", (run_id, job_id)).fetchone()
    if job is None:
        raise RunError(404, "job not found")
    module, inst, _cert, row = ctx.load_item(conn, job["instance_id"])
    attempts = []
    for a in conn.execute("SELECT * FROM attempts WHERE job_id=? ORDER BY number", (job_id,)):
        d = dict(a)
        d["request"] = jload(d.pop("request_json"))
        d["response"] = jload(d.pop("response_json"))
        attempts.append(d)
    ev = conn.execute("SELECT * FROM evaluations WHERE evaluation_id=?", (job["evaluation_id"],)).fetchone()
    return {
        "job": dict(job), "instance_id": job["instance_id"], "tier": job["tier"],
        "prompt": module.render_prompt(inst).model_dump(mode="json"),
        "certificate_hash": row["core_hash"], "certificate_verified": bool(row["verified"]),
        "max_objective": row["max_objective"],
        "attempts": attempts,
        "evaluation": jload(ev["envelope_json"]) if ev else None,
    }
