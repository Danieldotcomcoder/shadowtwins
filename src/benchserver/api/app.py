"""FastAPI application: JSON API under ``/api``, SSE progress, and the compiled frontend at ``/``.

Security posture (single operator): run controls require operator authorization (see ``auth``);
everything else is read-only. Request bodies are bounded, model output is only ever returned as
JSON data, queries are parameterized, and nothing executes model-generated content.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import ipaddress
import json
import logging
import sqlite3
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
)
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from benchcore import registry
from benchcore.contracts import SUITE_BENCHMARKS, SUITE_ID, SUITE_VERSION, RunState

from .. import catalog, costs, events, exports, leaderboard, runs
from ..context import AppContext
from ..db import backup as db_backup
from ..db import jdump, jload, latest_migration, now, schema_version, tx
from ..profiles import PROFILE_BY_ID, PROFILES, compatibility
from ..worker import Worker, worker_health
from . import schemas as S

log = logging.getLogger("benchserver.api")
TERMINAL = {s.value for s in (RunState.COMPLETED, RunState.INCOMPLETE, RunState.CANCELLED)}


# --- middleware ---------------------------------------------------------------------------------

class BodyLimit:
    """Reject request bodies above ``limit`` bytes (declared or streamed)."""

    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app, self.limit = app, limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for k, v in scope.get("headers", []):
            if k == b"content-length" and v.isdigit() and int(v) > self.limit:
                await JSONResponse({"detail": "request body too large"}, status_code=413)(scope, receive, send)
                return
        seen = 0

        async def limited() -> Message:
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > self.limit:
                    raise HTTPException(413, "request body too large")
            return msg

        await self.app(scope, limited, send)


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                               "script-src 'self'; connect-src 'self'; font-src 'self' data:; frame-ancestors 'none'",
}


# --- dependencies ------------------------------------------------------------------------------

def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def get_conn(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Iterator[sqlite3.Connection]:
    conn = ctx.connect()
    try:
        yield conn
    finally:
        conn.close()


Ctx = Annotated[AppContext, Depends(get_ctx)]
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def operator_status(request: Request, ctx: AppContext) -> tuple[bool, str]:
    mode = ctx.settings.auth_mode
    if mode == "open":
        return True, "open mode: every client may control runs"
    if mode == "readonly":
        return False, "server is read-only"
    header = request.headers.get("authorization", "")
    token = ctx.settings.operator_token
    if token and header.startswith("Bearer ") and hmac.compare_digest(header[7:].encode(), token.encode()):
        return True, "operator token"
    if mode == "token":
        return False, "operator token required"
    # local mode: loopback clients only
    host = request.client.host if request.client else None
    if _is_loopback(host):
        return True, "loopback client"
    return False, "run controls are limited to localhost; set ST_OPERATOR_TOKEN to allow remote operators"


def require_operator(request: Request, ctx: Ctx) -> None:
    ok, why = operator_status(request, ctx)
    if not ok:
        raise HTTPException(401 if "token" in why else 403, why)


Operator = Depends(require_operator)


def _err(exc: runs.RunError) -> HTTPException:
    return HTTPException(exc.status, {"message": exc.message, "detail": exc.detail})


# --- routers ------------------------------------------------------------------------------------

api = APIRouter(prefix="/api")


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "time": now()}


@api.get("/ready")
def ready(ctx: Ctx, conn: Conn) -> JSONResponse:
    checks: dict[str, Any] = {}
    checks["schema"] = {"version": schema_version(conn), "latest": latest_migration()}
    packs = conn.execute("SELECT split, COUNT(*) n FROM packs GROUP BY split").fetchall()
    checks["packs"] = {r["split"]: r["n"] for r in packs}
    checks["worker"] = worker_health(conn, ctx.settings.worker_stale_after_s)
    ok = (checks["schema"]["version"] >= checks["schema"]["latest"] and bool(checks["packs"].get("ranked"))
          and checks["worker"]["alive"] > 0)
    return JSONResponse({"ready": ok, "checks": checks}, status_code=200 if ok else 503)


def _pack_summaries(conn: sqlite3.Connection) -> list[S.PackSummary]:
    out = []
    for r in conn.execute("SELECT * FROM packs ORDER BY split, pack_id"):
        m = jload(r["manifest_json"])
        out.append(S.PackSummary(
            pack_id=r["pack_id"], benchmark_id=r["benchmark_id"], split=r["split"], ranked=bool(r["ranked"]),
            pack_hash=r["pack_hash"], policy_hash=r["policy_hash"], instances=len(m.get("items", [])),
            tiers=m.get("tiers", []), token_max=(m.get("token_report") or {}).get("max"),
            versions=m.get("versions", {})))
    return out


@api.get("/meta", response_model=S.Meta)
def meta(request: Request, ctx: Ctx, conn: Conn) -> S.Meta:
    ok, why = operator_status(request, ctx)
    return S.Meta(
        api_version=S.API_VERSION,
        suite={"id": SUITE_ID, "version": SUITE_VERSION, "benchmarks": list(SUITE_BENCHMARKS),
               "note": "Suite 1 contains one benchmark; the overall score equals the Shadow Twins score."},
        benchmarks=[registry.get(b).metadata().model_dump() for b in SUITE_BENCHMARKS],
        auth={"mode": ctx.settings.auth_mode, "operator": ok, "reason": why},
        providers={"openrouter": {"configured": ctx.settings.openrouter_configured},
                   "groq": {"configured": ctx.settings.groq_configured, "plan": ctx.settings.groq_plan},
                   "mock": {"enabled": "mock" in ctx.providers}},
        packs=_pack_summaries(conn),
        profiles=[S.Profile(**p.to_dict()) for p in PROFILES],
        modes=[{"id": m.value, **cfg, "label": {"quick_check": "Quick Check", "standard": "Standard",
                                                "repeated": "Repeated Evaluation"}[m.value]}
               for m, cfg in runs.MODES.items()],
    )


# --- catalog -----------------------------------------------------------------------------------

def _prompt_estimate(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(tokens_max) FROM instances").fetchone()
    return costs.prompt_estimate(row[0])


@api.get("/catalog", response_model=S.Catalog)
async def get_catalog(ctx: Ctx, conn: Conn, q: str | None = None) -> S.Catalog:
    data = await catalog.catalog(ctx, conn)
    favs = catalog.get_pref(conn, "favorites", [])
    recents = catalog.get_pref(conn, "recents", [])
    pt = _prompt_estimate(conn)
    models = []
    for d in data["models"]:
        if q and q.lower() not in (d["model_id"] + " " + d["name"]).lower():
            continue
        m = catalog.model_from_dict(d)
        models.append(S.CatalogModel(**d, favorite=d["model_id"] in favs,
                                     compat=[S.Compat(**compatibility(m, p, pt)) for p in PROFILES]))
    return S.Catalog(models=models, snapshots=data["snapshots"], errors=data["errors"],
                     favorites=favs, recents=recents)


@api.post("/catalog/refresh", response_model=S.Catalog, dependencies=[Operator])
async def refresh_catalog(ctx: Ctx, conn: Conn) -> S.Catalog:
    await catalog.catalog(ctx, conn, force=True)
    return await get_catalog(ctx, conn)


@api.get("/catalog/endpoints", response_model=S.Endpoints)
async def get_endpoints(ctx: Ctx, conn: Conn, model_id: str) -> S.Endpoints:
    try:
        eps, err = await catalog.endpoints(ctx, conn, model_id)
    except LookupError as exc:
        raise HTTPException(400, str(exc)) from exc
    found = catalog.find_model(conn, ctx.provider_name_for(model_id), model_id)
    pt = _prompt_estimate(conn)
    out = []
    for e in eps:
        compat = [S.Compat(**compatibility(found[0], p, pt, e)) for p in PROFILES] if found else []
        out.append(S.Endpoint(**e.to_dict(), compat=compat))
    return S.Endpoints(model_id=model_id, endpoints=out, error=err)


@api.put("/favorites", dependencies=[Operator])
def put_favorite(conn: Conn, body: dict[str, Any]) -> dict[str, Any]:
    model_id = str(body.get("model_id", ""))[:200]
    if not model_id:
        raise HTTPException(400, "model_id required")
    return {"favorites": catalog.toggle_favorite(conn, model_id, bool(body.get("favorite", True)))}


@api.get("/profiles", response_model=list[S.Profile])
def get_profiles() -> list[S.Profile]:
    return [S.Profile(**p.to_dict()) for p in PROFILES]


# --- packs and instances ----------------------------------------------------------------------

@api.get("/packs", response_model=list[S.PackSummary])
def get_packs(conn: Conn) -> list[S.PackSummary]:
    return _pack_summaries(conn)


@api.get("/packs/{pack_id}")
def get_pack(conn: Conn, pack_id: str) -> dict[str, Any]:
    r = conn.execute("SELECT manifest_json FROM packs WHERE pack_id=?", (pack_id,)).fetchone()
    if r is None:
        raise HTTPException(404, "pack not found")
    return jload(r["manifest_json"])


def _instance_summary(r: sqlite3.Row) -> S.InstanceSummary:
    core = (jload(r["instance_json"]) or {}).get("core", {})
    return S.InstanceSummary(instance_id=r["instance_id"], pack_id=r["pack_id"], tier=r["tier"], ord=r["ord"],
                             budget=core.get("budget"), entrances=len(core.get("entrances", [])),
                             editable=len(core.get("editable", [])), tokens_max=r["tokens_max"])


@api.get("/instances/{instance_id}")
def get_instance(ctx: Ctx, conn: Conn, instance_id: str, reveal: bool = False) -> dict[str, Any]:
    try:
        module, inst, cert, row = ctx.load_item(conn, instance_id)
    except KeyError as exc:
        raise HTTPException(404, "instance not found") from exc
    pack = conn.execute("SELECT split, ranked FROM packs WHERE pack_id=?", (row["pack_id"],)).fetchone()
    cert_doc = cert.model_dump(mode="json")
    if not reveal and pack["split"] == "practice":
        cert_doc = {"core_hash": cert_doc["core_hash"], "hidden": "practice certificate revealed after submission"}
    return {"instance": inst.model_dump(mode="json"), "certificate": cert_doc,
            "certificate_verified": bool(row["verified"]), "max_objective": row["max_objective"],
            "pack_id": row["pack_id"], "split": pack["split"], "ranked": bool(pack["ranked"]), "tier": row["tier"],
            "prompt": module.render_prompt(inst).model_dump(mode="json"), "tokens_max": row["tokens_max"]}


@api.get("/instances/{instance_id}/replay")
def get_replay(ctx: Ctx, conn: Conn, instance_id: str, run_id: str | None = None,
               job_id: int | None = None) -> dict[str, Any]:
    try:
        module, inst, cert, _row = ctx.load_item(conn, instance_id)
    except KeyError as exc:
        raise HTTPException(404, "instance not found") from exc
    envelope = None
    if job_id is not None:
        ev = conn.execute("SELECT envelope_json FROM evaluations WHERE job_id=? AND instance_id=?" +
                          (" AND run_id=?" if run_id else ""),
                          (job_id, instance_id, run_id) if run_id else (job_id, instance_id)).fetchone()
        if ev is None:
            raise HTTPException(404, "no evaluation for this job")
        from benchcore.contracts import EvaluationEnvelope

        envelope = EvaluationEnvelope.model_validate_json(ev["envelope_json"])
    return module.build_replay(inst, cert, envelope).model_dump(mode="json")


# --- runs ----------------------------------------------------------------------------------------

@api.post("/runs/estimate", response_model=S.RunPlan)
async def estimate_run(ctx: Ctx, conn: Conn, body: S.RunCreate) -> Any:
    try:
        return await runs.plan(ctx, conn, body, body.pack_id)
    except runs.RunError as exc:
        raise _err(exc) from exc


@api.post("/runs", response_model=S.RunSummary, status_code=201, dependencies=[Operator])
async def create_run(ctx: Ctx, conn: Conn, body: S.RunCreate) -> Any:
    try:
        run_id = await runs.create(ctx, conn, body, body.pack_id)
    except runs.RunError as exc:
        raise _err(exc) from exc
    return runs.summary(conn, run_id)


@api.get("/runs", response_model=list[S.RunSummary])
def list_runs(conn: Conn, model_id: str | None = None, limit: Annotated[int, Query(ge=1, le=500)] = 100) -> Any:
    return runs.list_runs(conn, model_id, limit)


@api.get("/runs/{run_id}", response_model=S.RunSummary)
def get_run(conn: Conn, run_id: str) -> Any:
    try:
        return runs.summary(conn, run_id)
    except runs.RunError as exc:
        raise _err(exc) from exc


@api.get("/runs/{run_id}/items", response_model=list[S.RunItem])
def get_items(conn: Conn, run_id: str) -> Any:
    try:
        return runs.items(conn, run_id)
    except runs.RunError as exc:
        raise _err(exc) from exc


@api.get("/runs/{run_id}/items/{job_id}")
def get_item(ctx: Ctx, conn: Conn, run_id: str, job_id: int) -> dict[str, Any]:
    try:
        return runs.job_detail(ctx, conn, run_id, job_id)
    except runs.RunError as exc:
        raise _err(exc) from exc


@api.post("/runs/{run_id}/actions/{action}", response_model=S.RunSummary, dependencies=[Operator])
def run_action(conn: Conn, run_id: str, action: str, body: S.ActionBody | None = None) -> Any:
    try:
        return runs.control(conn, run_id, action, body.value if body else None)
    except runs.RunError as exc:
        raise _err(exc) from exc


@api.get("/runs/{run_id}/events")
async def run_events(request: Request, ctx: Ctx, run_id: str, after: int | None = None) -> StreamingResponse:
    """Server-sent events. Resume with the ``Last-Event-ID`` header (or ``?after=``). Without either,
    the stream starts with a ``snapshot`` event carrying the current run summary."""
    conn = ctx.connect()
    try:
        runs.summary(conn, run_id)
    except runs.RunError as exc:
        conn.close()
        raise _err(exc) from exc
    header = request.headers.get("last-event-id")
    cursor = int(header) if header and header.isdigit() else after

    async def gen() -> AsyncIterator[str]:
        nonlocal cursor
        try:
            yield "retry: 2000\n\n"
            if cursor is None:
                snap = runs.summary(conn, run_id)
                cursor = snap["last_event_id"]
                yield f"id: {cursor}\nevent: snapshot\ndata: {json.dumps(snap)}\n\n"
            last_beat = asyncio.get_running_loop().time()
            while True:
                if await request.is_disconnected():
                    break
                batch = events.fetch(conn, run_id, cursor)
                for e in batch:
                    cursor = e["id"]
                    yield f"id: {e['id']}\nevent: {e['type']}\ndata: {json.dumps(e)}\n\n"
                if not batch:
                    state = conn.execute("SELECT state FROM runs WHERE run_id=?", (run_id,)).fetchone()["state"]
                    if state in TERMINAL:
                        yield f"id: {cursor}\nevent: end\ndata: {json.dumps({'state': state})}\n\n"
                        break
                    t = asyncio.get_running_loop().time()
                    if t - last_beat > 15:
                        yield ": keep-alive\n\n"
                        last_beat = t
                    await asyncio.sleep(0.4)
        finally:
            conn.close()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@api.get("/runs/{run_id}/export")
def export_run(ctx: Ctx, conn: Conn, run_id: str, format: str = "json") -> Response:
    try:
        runs.summary(conn, run_id)
    except runs.RunError as exc:
        raise _err(exc) from exc
    if format == "csv":
        return PlainTextResponse(exports.export_csv(conn, run_id), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="{run_id}.csv"'})
    if format != "json":
        raise HTTPException(400, "format must be json or csv")
    return JSONResponse(exports.export_json(ctx, conn, run_id),
                        headers={"Content-Disposition": f'attachment; filename="{run_id}.json"'})


@api.get("/runs/{run_id}/reevaluate")
def reevaluate_run(ctx: Ctx, conn: Conn, run_id: str) -> dict[str, Any]:
    try:
        runs.summary(conn, run_id)
    except runs.RunError as exc:
        raise _err(exc) from exc
    return exports.reevaluate(ctx, conn, run_id)


# --- leaderboard, models ---------------------------------------------------------------------

@api.get("/leaderboard", response_model=S.Leaderboard)
def get_leaderboard(conn: Conn, track: str = "standard", profile_id: str | None = None) -> Any:
    if track not in ("standard", "repeated"):
        raise HTTPException(400, "track must be standard or repeated")
    if profile_id is not None and profile_id not in PROFILE_BY_ID:
        raise HTTPException(400, "unknown profile")
    return leaderboard.leaderboard(conn, track, profile_id)


@api.get("/models/detail", response_model=S.ModelDetail)
def get_model_detail(conn: Conn, model_id: str) -> Any:
    return leaderboard.model_detail(conn, model_id)


# --- practice (unranked, human) --------------------------------------------------------------

@api.get("/practice", response_model=list[S.InstanceSummary])
def list_practice(conn: Conn) -> list[S.InstanceSummary]:
    rows = conn.execute("SELECT i.* FROM instances i JOIN packs p USING(pack_id) WHERE p.split='practice' "
                        "ORDER BY p.pack_id, i.ord").fetchall()
    return [_instance_summary(r) for r in rows]


@api.post("/practice/{instance_id}/submit")
def practice_submit(ctx: Ctx, conn: Conn, instance_id: str, body: S.PracticeSubmit) -> dict[str, Any]:
    r = conn.execute("SELECT p.split FROM instances i JOIN packs p USING(pack_id) WHERE instance_id=?",
                     (instance_id,)).fetchone()
    if r is None or r["split"] != "practice":
        raise HTTPException(404, "practice instance not found")
    module, inst, cert, _ = ctx.load_item(conn, instance_id)
    text = json.dumps({"remove": body.remove, "add": body.add})
    env = module.evaluate(inst, cert, text, None)
    with tx(conn):
        conn.execute("INSERT INTO practice_attempts(instance_id, created_at, edit_json, valid, score) "
                     "VALUES (?,?,?,?,?)", (instance_id, now(), jdump(body.model_dump()), int(env.valid), env.score))
    return {"unranked": True, "evaluation": env.model_dump(mode="json"),
            "replay": module.build_replay(inst, cert, env).model_dump(mode="json")}


# --- admin -----------------------------------------------------------------------------------

@api.post("/admin/backup", dependencies=[Operator])
def admin_backup(ctx: Ctx) -> dict[str, Any]:
    dest = ctx.settings.data_dir / "backups" / f"shadowtwins-{now()[:19].replace(':', '')}.db"
    return db_backup(ctx.settings.db_path, dest)


@api.get("/admin/workers")
def admin_workers(ctx: Ctx, conn: Conn) -> dict[str, Any]:
    return worker_health(conn, ctx.settings.worker_stale_after_s)


# --- app factory ------------------------------------------------------------------------------

def _mount_frontend(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        if path.startswith("api/"):
            raise HTTPException(404, "not found")
        target = (dist / path).resolve()
        if path and target.is_file() and dist.resolve() in target.parents:
            headers = {"Cache-Control": "public, max-age=31536000, immutable"} if path.startswith("assets/") else {}
            return FileResponse(target, headers=headers)
        if index.exists():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return PlainTextResponse("Frontend not built. Run `pnpm --dir frontend build`.", status_code=404)


def create_app(ctx: AppContext, embedded_worker: bool = False) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        stop = asyncio.Event()
        task = None
        if embedded_worker:
            worker = Worker(ctx)
            task = asyncio.create_task(worker.run(stop))
        yield
        stop.set()
        if task:
            await task
        await ctx.aclose()

    app = FastAPI(title="Shadow Twins API", version=S.API_VERSION, lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.state.ctx = ctx

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response

    app.add_middleware(BodyLimit, limit=ctx.settings.max_body_bytes)
    app.include_router(api)
    _mount_frontend(app, ctx.settings.frontend_dist)
    return app
