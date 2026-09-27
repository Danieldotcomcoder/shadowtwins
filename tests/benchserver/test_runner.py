import asyncio
import json

import pytest

from benchcore.aggregate import ScoredItem, aggregate
from benchcore.contracts import RunMode, RunSpec
from benchserver import costs, exports, runs
from benchserver.db import after, jdump, now, tx
from benchserver.worker import Worker

from .conftest import BackgroundWorker, create_run, drain, q, summary, wait_for


def test_quick_check_optimal_records_full_provenance(ctx):
    run_id = create_run(ctx, "mock/optimal")
    drain(ctx)
    s = summary(ctx, run_id)
    assert s["state"] == "completed" and s["scores"]["official"]
    assert s["scores"]["overall"] == 100.0 and s["scores"]["completed"] == s["scores"]["scheduled"] == 9
    assert s["scores"]["valid_rate"] == 1.0 and s["scores"]["optimal_rate"] == 1.0
    assert s["is_mock"] and not s["ranked"] and not s["leaderboard_eligible"]
    assert s["versions"]["evaluator"].startswith("st-eval-") and s["versions"]["suite"] == "suite-1"
    assert s["fingerprint"].startswith("sha256:")
    attempts = q(ctx, "SELECT * FROM attempts WHERE run_id=?", (run_id,))
    assert len(attempts) == 9
    for a in attempts:
        req = json.loads(a["request_json"])
        assert req["model"] == "mock/optimal" and req["messages"][0]["role"] == "user"
        assert req["max_tokens"] == 8192 and "tools" not in req and "response_format" not in req
        assert a["state"] == "response" and a["cost_source"] == "reported" and a["prompt_hash"].startswith("sha256:")
    evs = q(ctx, "SELECT e.certificate_hash, c.core_hash FROM evaluations e JOIN certificates c USING(instance_id) "
                 "WHERE e.run_id=?", (run_id,))
    assert len(evs) == 9 and all(e["certificate_hash"] == e["core_hash"] for e in evs)
    types = [e["type"] for e in q(ctx, "SELECT type FROM events WHERE run_id=? ORDER BY event_id", (run_id,))]
    assert types[0] == "run_created" and types.count("job_completed") == 9 and types[-1] == "run_state"


def test_scores_match_offline_recomputation_and_exports(ctx):
    run_id = create_run(ctx, "mock/random", RunMode.STANDARD, concurrency=8)
    drain(ctx)
    s = summary(ctx, run_id)
    assert s["state"] == "completed" and s["scores"]["scheduled"] == 30
    conn = ctx.connect()
    try:
        report = exports.reevaluate(ctx, conn, run_id)
        assert report["checked"] == 30 and report["mismatches"] == [] and report["aggregate_matches"]
        rows = list(__import__("csv").DictReader(exports.export_csv(conn, run_id).splitlines()))
        exported = exports.export_json(ctx, conn, run_id)
    finally:
        conn.close()
    items = [ScoredItem(r["instance_id"], r["tier"], int(r["repetition"]), r["job_state"],
                        float(r["score"]), r["valid"] == "1", None, r["category"] or None) for r in rows]
    offline = aggregate(items)
    assert offline["overall"] == s["scores"]["overall"] and offline["tiers"] == s["scores"]["tiers"]
    assert offline["interval_95"] == s["scores"]["interval_95"]
    # tier-equal aggregation by hand
    tiers = {}
    for it in items:
        tiers.setdefault(it.tier, []).append(it.score)
    manual = sum(sum(v) / len(v) for v in tiers.values()) / len(tiers)
    assert abs(manual - s["scores"]["overall"]) < 1e-12
    assert len(exported["items"]) == 30
    first = exported["items"][0]
    assert first["instance"]["core"]["occupancy"] and first["certificate"]["core"]["v_star"] >= 2
    assert first["evaluation"]["benchmark_id"] == "shadow_twins"


def test_repeated_track_averages_repetitions(ctx):
    run_id = create_run(ctx, "mock/random", RunMode.REPEATED, concurrency=8, limit=20)
    drain(ctx)
    s = summary(ctx, run_id)
    assert s["track"] == "repeated" and s["repetitions"] == 3 and s["scores"]["scheduled"] == 90
    assert s["scores"]["instances"] == 30  # repetitions do not become independent samples
    std = create_run(ctx, "mock/random", RunMode.STANDARD, concurrency=8)
    drain(ctx)
    # the mock answers deterministically per prompt, so averaging three identical repetitions is a no-op
    assert summary(ctx, std)["scores"]["overall"] == pytest.approx(s["scores"]["overall"])


def test_transient_errors_are_retried_with_bounded_backoff(ctx):
    run_id = create_run(ctx, "mock/flaky")
    drain(ctx)
    s = summary(ctx, run_id)
    assert s["state"] == "completed" and s["scores"]["overall"] == 100.0
    jobs = q(ctx, "SELECT attempts FROM jobs WHERE run_id=?", (run_id,))
    assert all(j["attempts"] == 2 for j in jobs)
    assert len(q(ctx, "SELECT * FROM evaluations WHERE run_id=?", (run_id,))) == 9
    failed = q(ctx, "SELECT * FROM attempts WHERE run_id=? AND state='failed'", (run_id,))
    assert len(failed) == 9 and all(a["error_category"] == "server_error" and a["retryable"] for a in failed)

    rl = create_run(ctx, "mock/ratelimit")
    drain(ctx)
    assert summary(ctx, rl)["state"] == "completed"
    assert all(j["attempts"] == 3 for j in q(ctx, "SELECT attempts FROM jobs WHERE run_id=?", (rl,)))
    retries = q(ctx, "SELECT payload_json FROM events WHERE run_id=? AND type='job_retry_scheduled'", (rl,))
    assert retries and all(json.loads(r["payload_json"])["delay_s"] >= 0.05 for r in retries)  # honours Retry-After


def test_completed_answers_are_never_retried(ctx):
    for model, category in [("mock/invalid", "malformed_json"), ("mock/refuse", "refusal"),
                            ("mock/truncated", "truncated")]:
        run_id = create_run(ctx, model)
        drain(ctx)
        s = summary(ctx, run_id)
        assert s["state"] == "completed" and s["scores"]["official"]
        assert s["scores"]["overall"] == 0.0 and s["scores"]["valid_rate"] == 0.0
        assert s["scores"]["categories"] == {category: 9}
        assert all(j["attempts"] == 1 for j in q(ctx, "SELECT attempts FROM jobs WHERE run_id=?", (run_id,)))


def test_ambiguous_requests_become_uncertain_and_block_official_totals(ctx):
    run_id = create_run(ctx, "mock/ambiguous")
    drain(ctx)
    s = summary(ctx, run_id)
    assert s["state"] == "incomplete" and not s["scores"]["official"] and s["scores"]["overall"] is None
    assert s["scores"]["states"] == {"uncertain": 9} and s["scores"]["completed"] == 0
    assert s["cost"]["uncertain_cost_attempts"] == 9 and s["cost"]["spent_usd"] > 0  # conservatively charged
    assert all(j["attempts"] == 1 for j in q(ctx, "SELECT attempts FROM jobs WHERE run_id=?", (run_id,)))
    conn = ctx.connect()
    try:
        runs.control(conn, run_id, "rerun_uncertain")
    finally:
        conn.close()
    ev = q(ctx, "SELECT payload_json FROM events WHERE run_id=? AND type='jobs_requeued'", (run_id,))
    assert "charged" in json.loads(ev[0]["payload_json"])["note"]
    drain(ctx)
    s = summary(ctx, run_id)
    assert s["state"] == "completed" and s["scores"]["overall"] == 100.0
    assert len(q(ctx, "SELECT * FROM attempts WHERE run_id=?", (run_id,))) == 18  # every attempt retained


def test_restart_recovery(ctx):
    run_id = create_run(ctx, "mock/optimal", concurrency=8)
    jobs = q(ctx, "SELECT job_id, instance_id FROM jobs WHERE run_id=? ORDER BY ord", (run_id,))
    conn = ctx.connect()
    dead = "w-dead-1"
    try:
        with tx(conn):
            conn.execute("INSERT INTO workers(worker_id, pid, started_at, heartbeat_at, state) VALUES (?,?,?,?,?)",
                         (dead, 1, now(), after(-3600), "running"))
            for n, (job, state) in enumerate(zip(jobs[:3], ["prepared", "sent", "response"], strict=True)):
                conn.execute("UPDATE jobs SET state='leased', lease_owner=?, lease_expires_at=?, attempts=1, "
                             "reserved_usd=0.01 WHERE job_id=?", (dead, after(-60), job["job_id"]))
                conn.execute("UPDATE runs SET reserved_usd=reserved_usd+0.01 WHERE run_id=?", (run_id,))
                content = None
                if state == "response":
                    module, inst, cert, _ = ctx.load_item(conn, job["instance_id"])
                    content = module.reference_answer(inst, cert)
                conn.execute("INSERT INTO attempts(job_id, run_id, number, state, worker_id, created_at, request_json, "
                             "prompt_hash, content, finish_reason, cost_usd, cost_source) VALUES "
                             "(?,?,?,?,?,?,?,?,?,?,?,?)",
                             (job["job_id"], run_id, 1, state, dead, now(), jdump({}), f"h{n}", content,
                              "stop" if content else None, 0.001 if content else None,
                              "reported" if content else None))
    finally:
        conn.close()
    drain(ctx)
    by_job = {j["job_id"]: j for j in q(ctx, "SELECT * FROM jobs WHERE run_id=?", (run_id,))}
    prepared, sent, responded = (by_job[j["job_id"]] for j in jobs[:3])
    assert prepared["state"] == "completed" and prepared["attempts"] == 2  # requeued, then sent normally
    assert sent["state"] == "uncertain"  # never silently re-sent
    assert responded["state"] == "completed"
    assert len(q(ctx, "SELECT * FROM attempts WHERE job_id=?", (responded["job_id"],))) == 1  # no new request
    abandoned = q(ctx, "SELECT state FROM attempts WHERE job_id=? ORDER BY attempt_id", (prepared["job_id"],))
    assert [a["state"] for a in abandoned] == ["abandoned", "response"]
    s = summary(ctx, run_id)
    assert s["state"] == "incomplete" and s["scores"]["states"] == {"completed": 8, "uncertain": 1}
    assert s["cost"]["reserved_usd"] == pytest.approx(0.0, abs=1e-9)


def test_pause_resume_and_cancel(ctx):
    run_id = create_run(ctx, "mock/slow", concurrency=1)
    conn = ctx.connect()
    try:
        with BackgroundWorker(ctx):
            wait_for(lambda: q(ctx, "SELECT COUNT(*) n FROM jobs WHERE run_id=? AND state='leased'", (run_id,))[0]["n"] == 1)
            runs.control(conn, run_id, "pause")
            wait_for(lambda: q(ctx, "SELECT COUNT(*) n FROM jobs WHERE run_id=? AND state='leased'", (run_id,))[0]["n"] == 0)
            done = q(ctx, "SELECT COUNT(*) n FROM jobs WHERE run_id=? AND state='completed'", (run_id,))[0]["n"]
            assert done >= 1  # the in-flight request settled
            asyncio.run(asyncio.sleep(0.5))
            assert q(ctx, "SELECT COUNT(*) n FROM jobs WHERE run_id=? AND state='completed'", (run_id,))[0]["n"] == done
            assert summary(ctx, run_id)["state"] == "paused"
            runs.control(conn, run_id, "resume")
            wait_for(lambda: summary(ctx, run_id)["state"] == "completed", timeout=20)

        run2 = create_run(ctx, "mock/slow", concurrency=1)
        with BackgroundWorker(ctx):
            wait_for(lambda: q(ctx, "SELECT COUNT(*) n FROM jobs WHERE run_id=? AND state='leased'", (run2,))[0]["n"] == 1)
            runs.control(conn, run2, "cancel")
            wait_for(lambda: summary(ctx, run2)["state"] == "cancelled")
        s = summary(ctx, run2)
        assert s["scores"]["states"].get("cancelled", 0) >= 7
        assert s["scores"]["states"].get("completed", 0) >= 1  # in-flight disposition recorded
        assert not s["scores"]["official"]
        with pytest.raises(runs.RunError):
            runs.control(conn, run2, "resume")
    finally:
        conn.close()


def test_spending_limit_stops_dispatch_and_can_be_raised(ctx):
    conn = ctx.connect()
    try:
        spec = RunSpec(model_id="mock/optimal", profile_id="standard", mode=RunMode.QUICK_CHECK,
                       spend_limit_usd=1.0, concurrency=1)
        plan = asyncio.run(runs.plan(ctx, conn, spec))
        per_call = plan["estimate"]["max_per_call_usd"]
        assert plan["estimate"]["worst_case_usd"] == pytest.approx(
            sum(costs.reservation(plan["pricing"], r["tokens_max"], 8192)
                for r in q(ctx, "SELECT tokens_max FROM instances WHERE pack_id='shadowtwins-practice-v1'")))
        run_id = create_run(ctx, "mock/optimal", limit=per_call * 1.02, concurrency=1)
        drain(ctx)
        s = summary(ctx, run_id)
        assert s["state"] == "budget_stopped" and s["scores"]["completed"] == 1
        assert s["cost"]["spent_usd"] <= s["cost"]["spend_limit_usd"] and s["cost"]["reserved_usd"] == 0
        with pytest.raises(runs.RunError):
            runs.control(conn, run_id, "set_spend_limit", 0.0000001)
        runs.control(conn, run_id, "set_spend_limit", 1.0)
        runs.control(conn, run_id, "resume")
        drain(ctx)
        assert summary(ctx, run_id)["state"] == "completed"
        # a limit below one call's reservation cannot start at all
        low = RunSpec(model_id="mock/optimal", profile_id="standard", mode=RunMode.QUICK_CHECK,
                      spend_limit_usd=per_call / 2)
        with pytest.raises(runs.RunError, match="reservation"):
            asyncio.run(runs.create(ctx, conn, low))
    finally:
        conn.close()


def test_unknown_pricing_requires_explicit_unranked_override(ctx):
    conn = ctx.connect()
    try:
        spec = RunSpec(model_id="mock/unpriced", profile_id="standard", mode=RunMode.STANDARD, spend_limit_usd=1)
        with pytest.raises(runs.RunError, match="pricing is unknown"):
            asyncio.run(runs.create(ctx, conn, spec))
    finally:
        conn.close()
    run_id = create_run(ctx, "mock/unpriced", RunMode.STANDARD, allow_unknown=True, concurrency=8)
    drain(ctx)
    s = summary(ctx, run_id)
    assert s["state"] == "completed" and not s["ranked"]
    assert any("pricing unknown" in r for r in s["not_ranked_reasons"])
    assert s["cost"]["spent_usd"] == 0 and not s["cost"]["pricing_known"]


def test_run_blocking_and_final_provider_errors(ctx):
    run_id = create_run(ctx, "mock/nocredits")
    drain(ctx)
    s = summary(ctx, run_id)
    assert s["state"] == "paused" and "insufficient_credits" in s["state_reason"]
    assert s["scores"]["states"] == {"queued": 9}
    bad = create_run(ctx, "mock/badrequest")
    drain(ctx)
    s = summary(ctx, bad)
    assert s["state"] == "incomplete" and s["scores"]["states"] == {"failed": 9}
    assert s["scores"]["scheduled"] == 9 and s["scores"]["completed"] == 0 and s["scores"]["overall"] is None


def test_mock_runs_are_never_ranked(ctx):
    run_id = create_run(ctx, "mock/optimal", RunMode.STANDARD, endpoint="mock-endpoint", concurrency=8)
    drain(ctx)
    s = summary(ctx, run_id)
    assert s["state"] == "completed" and not s["ranked"] and s["not_ranked_reasons"] == ["mock provider (test double)"]
    conn = ctx.connect()
    try:
        from benchserver.leaderboard import leaderboard

        assert leaderboard(conn)["rows"] == []
    finally:
        conn.close()


def _promote_to_real(ctx, run_id: str, provider_name: str = "Mock") -> None:
    """Test-only: relabel a finished mock run as an eligible ranked run to exercise listing policy."""
    conn = ctx.connect()
    try:
        with tx(conn):
            conn.execute("UPDATE runs SET is_mock=0, ranked=1, ranked_reasons_json='[]', provider='openrouter' "
                         "WHERE run_id=?", (run_id,))
            conn.execute("UPDATE attempts SET provider_name=? WHERE run_id=?", (provider_name, run_id))
    finally:
        conn.close()


def test_leaderboard_lists_latest_eligible_run_not_the_best(ctx):
    best = create_run(ctx, "mock/optimal", RunMode.STANDARD, endpoint="mock-endpoint", concurrency=8)
    drain(ctx)
    _promote_to_real(ctx, best)
    later_and_worse = create_run(ctx, "mock/optimal", RunMode.STANDARD, endpoint="mock-endpoint", concurrency=8)
    drain(ctx)
    conn = ctx.connect()
    try:
        with tx(conn):  # make the later run score lower
            conn.execute("UPDATE evaluations SET score=0, valid=0, category='malformed_json', raw_objective=NULL "
                         "WHERE run_id=? AND job_id IN (SELECT job_id FROM jobs WHERE run_id=? AND tier='T1')",
                         (later_and_worse, later_and_worse))
        _promote_to_real(ctx, later_and_worse)
        # an incomplete, even later run is never listed
        incomplete = create_run(ctx, "mock/optimal", RunMode.STANDARD, endpoint="mock-endpoint", concurrency=8)
        with tx(conn):
            conn.execute("UPDATE runs SET state='incomplete', completed_at=? WHERE run_id=?", (now(), incomplete))
        _promote_to_real(ctx, incomplete)
        from benchserver.leaderboard import leaderboard, model_detail

        rows = leaderboard(conn)["rows"]
        assert len(rows) == 1
        row = rows[0]
        assert row["run_id"] == later_and_worse and row["overall"] == pytest.approx(200 / 3)
        assert row["overall"] == row["shadow_twins"] and row["runs_in_group"] == 2 and row["rank"] == 1
        detail = model_detail(conn, "mock/optimal")
        assert {r["run_id"] for r in detail["runs"]} >= {best, later_and_worse, incomplete}
        # observed provider contradicting the pin disqualifies the run
        _promote_to_real(ctx, later_and_worse, provider_name="SomeoneElse")
        assert leaderboard(conn)["rows"][0]["run_id"] == best
    finally:
        conn.close()


def test_worker_shutdown_leaves_sent_attempts_for_recovery(ctx):
    run_id = create_run(ctx, "mock/slow", concurrency=2)

    async def go():
        w = Worker(ctx, "w-shutdown")
        w.register()
        job = w.claim(run_id)
        task = asyncio.create_task(w.execute(job))
        w.inflight[job["job_id"]] = task
        await asyncio.sleep(0.05)
        await w.shutdown(grace_s=0.01)
        return job["job_id"]

    job_id = asyncio.run(go())
    assert q(ctx, "SELECT state FROM attempts WHERE job_id=?", (job_id,))[0]["state"] == "sent"
    drain(ctx)  # the stopped worker's lease is recovered immediately
    assert q(ctx, "SELECT state FROM jobs WHERE job_id=?", (job_id,))[0]["state"] == "uncertain"


def test_rate_limits_back_off_the_whole_run(tmp_path):
    import datetime as dt

    from benchserver.config import RetryPolicy

    from .conftest import make_ctx, make_settings

    ctx = make_ctx(make_settings(tmp_path, retry=RetryPolicy(
        max_attempts=4, base_delay_s=0.01, max_delay_s=0.05, rate_limit_base_delay_s=0.4, rate_limit_max_delay_s=0.8)))
    run_id = create_run(ctx, "mock/ratelimit", concurrency=4)
    drain(ctx, idle_s=1.0)
    s = summary(ctx, run_id)
    assert s["state"] == "completed"
    evs = q(ctx, "SELECT type, created_at, payload_json FROM events WHERE run_id=? ORDER BY event_id", (run_id,))
    cooldowns = [e for e in evs if e["type"] == "run_cooldown"]
    assert cooldowns, "a 429 must pause the run"
    starts = [dt.datetime.fromisoformat(e["created_at"]) for e in evs if e["type"] == "job_started"]
    for c in cooldowns:
        t0 = dt.datetime.fromisoformat(c["created_at"])
        window = json.loads(c["payload_json"])["seconds"] - 0.05
        assert not [t for t in starts if t0 < t < t0 + dt.timedelta(seconds=window)], "dispatched during cooldown"
    # rate limits use their own (longer) schedule and attempt budget
    delays = [json.loads(e["payload_json"])["delay_s"] for e in evs if e["type"] == "job_retry_scheduled"]
    assert min(delays) >= 0.4


def test_explicit_retry_starts_a_fresh_retry_budget(tmp_path):
    from benchserver.config import RetryPolicy
    from benchserver.providers.base import ErrorCategory
    from benchserver.providers.mock import MockProvider

    from .conftest import make_ctx, make_settings

    class AlwaysLimited(MockProvider):
        async def complete(self, req):
            return self._err(ErrorCategory.RATE_LIMITED, 429, "mock: always rate limited")

    ctx = make_ctx(make_settings(tmp_path, retry=RetryPolicy(
        max_attempts=4, base_delay_s=0.01, max_delay_s=0.05, rate_limit_max_attempts=2,
        rate_limit_base_delay_s=0.01, rate_limit_max_delay_s=0.02)))
    ctx.providers["mock"] = AlwaysLimited(ctx.answer_book)
    run_id = create_run(ctx, "mock/optimal", concurrency=9)
    drain(ctx)
    jobs = q(ctx, "SELECT state, attempts FROM jobs WHERE run_id=?", (run_id,))
    assert all(j["state"] == "failed" and j["attempts"] == 2 for j in jobs)
    conn = ctx.connect()
    try:
        runs.control(conn, run_id, "retry_failed")
    finally:
        conn.close()
    drain(ctx)
    jobs = q(ctx, "SELECT state, attempts, retry_base FROM jobs WHERE run_id=?", (run_id,))
    # a full second cycle of 2 attempts; numbering keeps counting for the audit trail
    assert all(j["state"] == "failed" and j["attempts"] == 4 and j["retry_base"] == 2 for j in jobs)
    assert len(q(ctx, "SELECT * FROM attempts WHERE run_id=?", (run_id,))) == 36
