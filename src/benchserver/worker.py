"""Durable worker: a separate process that leases jobs, calls providers and scores answers.

Guarantees and non-guarantees:

* Jobs are persisted before any request. A job is leased inside a ``BEGIN IMMEDIATE``
  transaction together with its cost reservation; leases are extended by heartbeats.
* Each attempt is recorded ``prepared`` before the network call and ``sent`` immediately before
  it. After a crash, stale leases are recovered: never-sent attempts are requeued safely; attempts
  with a stored response are evaluated without a new request; attempts that were sent but have
  no response become ``uncertain`` and are only rerun by an explicit, auditable operator action.
* Only eligible transport, server and rate-limit failures are retried, with the fixed policy in
  ``Settings.retry``. A completed answer — valid, invalid, refused or truncated — is never retried.
* Exactly-once execution across the remote API is **not** claimed.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import secrets
import signal
import socket
import sqlite3
import time
from typing import Any

from benchcore.contracts import CompletionMeta, FinishReason, JobState, RunState

from . import costs, events, runs
from .context import AppContext
from .db import after, jdump, jload, now, tx
from .providers.base import RUN_BLOCKING, CompletionRequest, CompletionResult, ErrorCategory

log = logging.getLogger("benchserver.worker")


def _finish_reason(s: str | None) -> FinishReason:
    try:
        return FinishReason(s) if s else FinishReason.UNKNOWN
    except ValueError:
        return FinishReason.UNKNOWN


class Worker:
    def __init__(self, ctx: AppContext, worker_id: str | None = None) -> None:
        self.ctx = ctx
        self.s = ctx.settings
        self.id = worker_id or f"w-{socket.gethostname()}-{os.getpid()}-{secrets.token_hex(2)}"
        self.conn = ctx.connect()
        self.inflight: dict[int, asyncio.Task[None]] = {}
        self.stopping = False
        self._last_hb = 0.0
        self._last_recover = 0.0
        self.run_cooldown: dict[str, float] = {}  # run_id -> monotonic time dispatch may resume

    # --- lifecycle -----------------------------------------------------------------------------
    def register(self) -> None:
        with tx(self.conn):
            self.conn.execute("INSERT INTO workers(worker_id, pid, started_at, heartbeat_at, state) VALUES "
                              "(?,?,?,?, 'running') ON CONFLICT(worker_id) DO UPDATE SET "
                              "heartbeat_at=excluded.heartbeat_at, state='running'",
                              (self.id, os.getpid(), now(), now()))

    def heartbeat(self) -> None:
        with tx(self.conn):
            self.conn.execute("UPDATE workers SET heartbeat_at=?, state=? WHERE worker_id=?",
                              (now(), "stopping" if self.stopping else "running", self.id))
            if self.inflight:
                ids = ",".join(str(i) for i in self.inflight)
                self.conn.execute(f"UPDATE jobs SET lease_expires_at=? WHERE lease_owner=? AND state='leased' "
                                  f"AND job_id IN ({ids})", (after(self.s.lease_ttl_s), self.id))
        self._last_hb = time.monotonic()

    async def run(self, stop: asyncio.Event | None = None, idle_exit_s: float | None = None) -> None:
        """Main loop. ``idle_exit_s`` (tests) exits after that long with nothing to do."""
        stop = stop or asyncio.Event()
        self.register()
        self.recover()
        idle_since: float | None = None
        while not stop.is_set():
            busy = await self.tick()
            if idle_exit_s is not None:
                if busy or self.inflight:
                    idle_since = None
                elif idle_since is None:
                    idle_since = time.monotonic()
                elif time.monotonic() - idle_since >= idle_exit_s:
                    break
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.s.poll_s)
        await self.shutdown()

    async def shutdown(self, grace_s: float = 30.0) -> None:
        self.stopping = True
        if self.inflight:
            log.info("waiting up to %.0fs for %d in-flight requests", grace_s, len(self.inflight))
            _, pending = await asyncio.wait(list(self.inflight.values()), timeout=grace_s)
            for t in pending:
                t.cancel()  # their attempts stay 'sent' and are recovered as uncertain
        with tx(self.conn):
            self.conn.execute("UPDATE workers SET state='stopped', heartbeat_at=? WHERE worker_id=?",
                              (now(), self.id))
        self.conn.close()

    async def tick(self) -> bool:
        mono = time.monotonic()
        if mono - self._last_hb >= self.s.heartbeat_s:
            self.heartbeat()
        if mono - self._last_recover >= max(1.0, self.s.lease_ttl_s / 3):
            self.recover()
            self._last_recover = mono
        busy = False
        if not self.stopping:
            active = [r["run_id"] for r in self.conn.execute(
                "SELECT run_id FROM runs WHERE state='active' ORDER BY created_at")]
            for run_id in active:
                while len(self.inflight) < self.s.worker_concurrency:
                    job = self.claim(run_id)
                    if job is None:
                        break
                    busy = True
                    task = asyncio.create_task(self.execute(job))
                    self.inflight[job["job_id"]] = task
                    task.add_done_callback(lambda _t, jid=job["job_id"]: self.inflight.pop(jid, None))
        for r in self.conn.execute("SELECT run_id FROM runs WHERE state IN ('active','cancelling')").fetchall():
            runs.finalize(self.conn, r["run_id"])
        return busy

    # --- claiming ------------------------------------------------------------------------------
    def claim(self, run_id: str) -> dict[str, Any] | None:
        if time.monotonic() < self.run_cooldown.get(run_id, 0.0):
            return None  # the run is backing off after a rate limit
        with tx(self.conn):
            run = self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None or run["state"] != RunState.ACTIVE.value:
                return None
            leased = self.conn.execute("SELECT COUNT(*) FROM jobs WHERE run_id=? AND state='leased'",
                                       (run_id,)).fetchone()[0]
            if leased >= run["concurrency"]:
                return None
            job = self.conn.execute(
                "SELECT j.*, i.tokens_max FROM jobs j JOIN instances i USING(instance_id) WHERE j.run_id=? AND "
                "(j.state='queued' OR (j.state='retry_wait' AND j.not_before <= ?)) ORDER BY j.ord LIMIT 1",
                (run_id, now())).fetchone()
            if job is None:
                return None
            budget = jload(run["request_template_json"])["params"]["max_tokens"]  # after model-limit capping
            reserve = costs.reservation(jload(run["pricing_json"]), job["tokens_max"], budget)
            if reserve is None:
                if not run["allow_unknown_pricing"]:
                    runs.set_state(self.conn, run_id, RunState.BUDGET_STOPPED,
                                   "pricing unknown; dispatch requires an explicit unranked override")
                    return None
                reserve = 0.0
            if run["spent_usd"] + run["reserved_usd"] + reserve > run["spend_limit_usd"] + 1e-12:
                if leased == 0:
                    runs.set_state(self.conn, run_id, RunState.BUDGET_STOPPED,
                                   f"remaining budget ${run['spend_limit_usd'] - run['spent_usd']:.4f} is below "
                                   f"the next reservation ${reserve:.4f}")
                return None
            cur = self.conn.execute(
                "UPDATE jobs SET state='leased', lease_owner=?, lease_expires_at=?, attempts=attempts+1, "
                "reserved_usd=?, updated_at=? WHERE job_id=? AND state IN ('queued','retry_wait')",
                (self.id, after(self.s.lease_ttl_s), reserve, now(), job["job_id"]))
            if cur.rowcount != 1:
                return None
            self.conn.execute("UPDATE runs SET reserved_usd=reserved_usd+?, updated_at=? WHERE run_id=?",
                              (reserve, now(), run_id))
            events.emit(self.conn, run_id, "job_started",
                        {"job_id": job["job_id"], "instance_id": job["instance_id"], "attempt": job["attempts"] + 1})
            return dict(job) | {"attempts": job["attempts"] + 1, "reserved_usd": reserve,
                                "template": jload(run["request_template_json"]),
                                "pricing": jload(run["pricing_json"])}

    # --- execution -----------------------------------------------------------------------------
    async def execute(self, job: dict[str, Any]) -> None:
        attempt_id: int | None = None
        stage = "prepare"
        try:
            module, inst, _cert, _ = self.ctx.load_item(self.conn, job["instance_id"])
            prompt = module.render_prompt(inst)
            t = job["template"]
            req = CompletionRequest(model_id=t["model_id"], messages=[m.model_dump() for m in prompt.messages],
                                    params=t["params"], endpoint=t["endpoint"], allow_fallbacks=t["allow_fallbacks"])
            with tx(self.conn):
                cur = self.conn.execute(
                    "INSERT INTO attempts(job_id, run_id, number, state, worker_id, created_at, request_json, "
                    "prompt_hash, reservation_usd) VALUES (?,?,?,?,?,?,?,?,?)",
                    (job["job_id"], job["run_id"], job["attempts"], "prepared", self.id, now(),
                     jdump(req.body()), prompt.text_hash, job["reserved_usd"]))
                attempt_id = int(cur.lastrowid or 0)
            with tx(self.conn):
                self.conn.execute("UPDATE attempts SET state='sent', sent_at=? WHERE attempt_id=?", (now(), attempt_id))
            stage = "sent"
            provider = self.ctx.provider_for(t["model_id"])
            result = await provider.complete(req)
            stage = "received"
            self.record(job, attempt_id, result)
            stage = "recorded"
            if result.ok:
                self.evaluate_stored(job["job_id"], attempt_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # internal error: never silently lose the job
            log.exception("job %s failed internally at stage %s", job["job_id"], stage)
            self.internal_failure(job, attempt_id, stage, exc)
        finally:
            runs.finalize(self.conn, job["run_id"])

    def _release(self, job_id: int, run_id: str, charge: float) -> None:
        row = self.conn.execute("SELECT reserved_usd FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        reserved = row["reserved_usd"] if row else 0.0
        self.conn.execute("UPDATE runs SET reserved_usd=MAX(0, reserved_usd-?), spent_usd=spent_usd+?, "
                          "updated_at=? WHERE run_id=?", (reserved, charge, now(), run_id))
        self.conn.execute("UPDATE jobs SET reserved_usd=0 WHERE job_id=?", (job_id,))

    def record(self, job: dict[str, Any], attempt_id: int, r: CompletionResult) -> None:
        run_id, job_id = job["run_id"], job["job_id"]
        with tx(self.conn):
            owned = self.conn.execute("SELECT 1 FROM jobs WHERE job_id=? AND state='leased' AND lease_owner=?",
                                      (job_id, self.id)).fetchone()
            common = (r.http_status, r.generation_id, r.provider_name, r.response_model, r.finish_reason,
                      r.native_finish_reason, r.content, r.refusal, r.reasoning_chars, r.usage.prompt_tokens,
                      r.usage.completion_tokens, r.usage.reasoning_tokens, r.latency_ms,
                      jdump(r.raw) if r.raw is not None else None)
            base_sql = ("http_status=?, generation_id=?, provider_name=?, response_model=?, finish_reason=?, "
                        "native_finish_reason=?, content=?, refusal=?, reasoning_chars=?, prompt_tokens=?, "
                        "completion_tokens=?, reasoning_tokens=?, latency_ms=?, response_json=?")
            if r.ok:
                cost, source = costs.actual_cost(r, job["pricing"])
                self.conn.execute(f"UPDATE attempts SET state='response', finished_at=?, cost_usd=?, cost_source=?, "
                                  f"{base_sql} WHERE attempt_id=?", (now(), cost, source, *common, attempt_id))
                if owned:
                    self._release(job_id, run_id, cost or 0.0)
                return
            # Failure: nothing to score. Decide retry / uncertain / fail / block.
            cat = r.error_category or ErrorCategory.SERVER
            if cat == ErrorCategory.AMBIGUOUS:
                charge, source = job["reserved_usd"], "reserved_uncertain"
            else:
                charge, source = 0.0, "none"
            self.conn.execute(f"UPDATE attempts SET state=?, finished_at=?, error_category=?, error_message=?, "
                              f"retryable=?, cost_usd=?, cost_source=?, {base_sql} WHERE attempt_id=?",
                              ("ambiguous" if cat == ErrorCategory.AMBIGUOUS else "failed", now(), cat.value,
                               r.error_message, int(r.retryable), charge if charge else None, source, *common,
                               attempt_id))
            if not owned:
                return
            self._release(job_id, run_id, charge)
            used = job["attempts"] - (job.get("retry_base") or 0)  # attempts in this retry cycle
            err = f"{cat.value}: {r.error_message or ''}"[:300]
            info = {"job_id": job_id, "instance_id": job["instance_id"], "category": cat.value,
                    "http_status": r.http_status, "attempt": job["attempts"]}
            if cat == ErrorCategory.AMBIGUOUS:
                self._set_job(job_id, JobState.UNCERTAIN, err)
                events.emit(self.conn, run_id, "job_uncertain", info | {
                    "note": "request may have been processed; rerun only by explicit operator action"})
            elif cat in RUN_BLOCKING:
                self._set_job(job_id, JobState.QUEUED, err)
                runs.set_state(self.conn, run_id, RunState.PAUSED, f"provider error blocks dispatch: {err}")
            elif cat == ErrorCategory.RATE_LIMITED and used < self.s.retry.rate_limit_max_attempts:
                delay = self.s.retry.rate_limit_delay(job["attempts"], r.retry_after_s)
                self._set_job(job_id, JobState.RETRY_WAIT, err, not_before=after(delay))
                # Back off the whole run: every other request would hit the same window.
                until = time.monotonic() + delay
                if until > self.run_cooldown.get(run_id, 0.0):
                    self.run_cooldown[run_id] = until
                    events.emit(self.conn, run_id, "run_cooldown", {"seconds": round(delay, 3),
                                                                     "reason": "provider rate limit"})
                events.emit(self.conn, run_id, "job_retry_scheduled", info | {"delay_s": round(delay, 3)})
            elif r.retryable and cat != ErrorCategory.RATE_LIMITED and used < self.s.retry.max_attempts:
                delay = self.s.retry.delay(job["attempts"], r.retry_after_s)
                self._set_job(job_id, JobState.RETRY_WAIT, err, not_before=after(delay))
                events.emit(self.conn, run_id, "job_retry_scheduled", info | {"delay_s": round(delay, 3)})
            else:
                self._set_job(job_id, JobState.FAILED, err)
                events.emit(self.conn, run_id, "job_failed", info | {
                    "reason": "retries exhausted" if r.retryable else "not retryable"})

    def _set_job(self, job_id: int, state: JobState, err: str | None = None, not_before: str | None = None) -> None:
        self.conn.execute("UPDATE jobs SET state=?, lease_owner=NULL, lease_expires_at=NULL, last_error=?, "
                          "not_before=?, updated_at=? WHERE job_id=?", (state.value, err, not_before, now(), job_id))

    def evaluate_stored(self, job_id: int, attempt_id: int) -> None:
        """Score a stored response. Deterministic; safe to repeat after a crash."""
        a = self.conn.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        job = self.conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        module, inst, cert, row = self.ctx.load_item(self.conn, job["instance_id"])
        meta = CompletionMeta(finish_reason=_finish_reason(a["finish_reason"]),
                              native_finish_reason=a["native_finish_reason"], refusal=a["refusal"])
        env = module.evaluate(inst, cert, a["content"] or "", meta)
        with tx(self.conn):
            cur_job = self.conn.execute("SELECT state FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if cur_job["state"] == JobState.COMPLETED.value:
                return
            cur = self.conn.execute(
                "INSERT INTO evaluations(job_id, attempt_id, run_id, instance_id, valid, category, score, "
                "raw_objective, max_objective, evaluator_version, certificate_hash, envelope_json, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (job_id, attempt_id, job["run_id"], job["instance_id"], int(env.valid), env.category, env.score,
                 env.raw_objective, env.max_objective, env.versions.get("evaluator", ""), row["core_hash"],
                 env.model_dump_json(), now()))
            self.conn.execute("UPDATE jobs SET state='completed', evaluation_id=?, lease_owner=NULL, "
                              "lease_expires_at=NULL, last_error=NULL, updated_at=? WHERE job_id=?",
                              (int(cur.lastrowid or 0), now(), job_id))
            events.emit(self.conn, job["run_id"], "job_completed", {
                "job_id": job_id, "instance_id": job["instance_id"], "tier": job["tier"],
                "repetition": job["repetition"], "valid": env.valid, "category": env.category,
                "score": env.score, "raw_objective": env.raw_objective, "max_objective": env.max_objective,
                "cost_usd": a["cost_usd"]})

    def internal_failure(self, job: dict[str, Any], attempt_id: int | None, stage: str, exc: Exception) -> None:
        msg = f"internal error at {stage}: {type(exc).__name__}: {exc}"[:300]
        with tx(self.conn):
            if attempt_id is not None and stage in ("prepare", "sent", "received"):
                self.conn.execute("UPDATE attempts SET state=?, finished_at=?, error_category='internal', "
                                  "error_message=? WHERE attempt_id=? AND state IN ('prepared','sent')",
                                  ("ambiguous" if stage != "prepare" else "abandoned", now(), msg, attempt_id))
            row = self.conn.execute("SELECT state FROM jobs WHERE job_id=?", (job["job_id"],)).fetchone()
            if row and row["state"] == "leased":
                sent = stage in ("sent", "received")
                self._release(job["job_id"], job["run_id"], job["reserved_usd"] if sent else 0.0)
                self._set_job(job["job_id"], JobState.UNCERTAIN if sent else JobState.FAILED, msg)
                events.emit(self.conn, job["run_id"], "job_uncertain" if sent else "job_failed",
                            {"job_id": job["job_id"], "instance_id": job["instance_id"], "category": "internal",
                             "reason": msg})

    # --- crash recovery ------------------------------------------------------------------------
    def recover(self) -> dict[str, int]:
        """Recover jobs whose lease expired or whose worker stopped/died."""
        stats = {"requeued": 0, "evaluated": 0, "uncertain": 0}
        stale_workers = {r[0] for r in self.conn.execute(
            "SELECT worker_id FROM workers WHERE worker_id<>? AND (state='stopped' OR heartbeat_at < ?)",
            (self.id, after(-self.s.worker_stale_after_s)))}
        rows = self.conn.execute("SELECT * FROM jobs WHERE state='leased'").fetchall()
        for job in rows:
            if job["lease_owner"] == self.id and job["job_id"] in self.inflight:
                continue
            expired = job["lease_expires_at"] is None or job["lease_expires_at"] < now()
            if not (expired or job["lease_owner"] in stale_workers):
                continue
            a = self.conn.execute("SELECT * FROM attempts WHERE job_id=? ORDER BY number DESC, attempt_id DESC "
                                  "LIMIT 1", (job["job_id"],)).fetchone()
            if a is not None and a["state"] == "response":
                with tx(self.conn):
                    if job["reserved_usd"]:  # response stored but reservation not yet settled
                        self._release(job["job_id"], job["run_id"], a["cost_usd"] or 0.0)
                    self.conn.execute("UPDATE jobs SET lease_owner=? WHERE job_id=?", (self.id, job["job_id"]))
                    events.emit(self.conn, job["run_id"], "job_recovered",
                                {"job_id": job["job_id"], "action": "evaluate stored response (no new request)"})
                self.evaluate_stored(job["job_id"], a["attempt_id"])
                stats["evaluated"] += 1
                continue
            with tx(self.conn):
                if a is None or a["state"] == "prepared":
                    if a is not None:
                        self.conn.execute("UPDATE attempts SET state='abandoned', finished_at=?, "
                                          "error_message='worker stopped before sending' WHERE attempt_id=?",
                                          (now(), a["attempt_id"]))
                    self._release(job["job_id"], job["run_id"], 0.0)
                    self._set_job(job["job_id"], JobState.QUEUED, "requeued: lease expired before sending")
                    events.emit(self.conn, job["run_id"], "job_recovered",
                                {"job_id": job["job_id"], "action": "requeued (never sent)"})
                    stats["requeued"] += 1
                else:
                    self.conn.execute("UPDATE attempts SET state='ambiguous', finished_at=?, "
                                      "error_category='ambiguous', error_message=?, cost_source='reserved_uncertain', "
                                      "cost_usd=? WHERE attempt_id=? AND state='sent'",
                                      (now(), "worker stopped after sending; outcome unknown",
                                       job["reserved_usd"] or None, a["attempt_id"]))
                    self._release(job["job_id"], job["run_id"], job["reserved_usd"])
                    self._set_job(job["job_id"], JobState.UNCERTAIN, "worker stopped after sending")
                    events.emit(self.conn, job["run_id"], "job_uncertain",
                                {"job_id": job["job_id"], "instance_id": job["instance_id"],
                                 "category": "ambiguous", "note": "recovered after a restart; rerun explicitly"})
                    stats["uncertain"] += 1
        return stats


def main(ctx: AppContext | None = None) -> None:
    from .app_state import startup

    ctx = ctx or startup(run_migrations=False)
    worker = Worker(ctx)
    stop = asyncio.Event()

    async def _main() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except (NotImplementedError, RuntimeError):  # Windows
                signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
        log.info("worker %s started", worker.id)
        await worker.run(stop)
        await ctx.aclose()
        log.info("worker %s stopped", worker.id)

    asyncio.run(_main())


def worker_health(conn: sqlite3.Connection, stale_after_s: float) -> dict[str, Any]:
    rows = [dict(r) for r in conn.execute("SELECT * FROM workers WHERE state<>'stopped' ORDER BY heartbeat_at DESC")]
    alive = [r for r in rows if r["heartbeat_at"] >= after(-stale_after_s)]
    return {"alive": len(alive), "workers": rows[:5]}
