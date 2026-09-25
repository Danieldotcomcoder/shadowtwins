"""Model catalog: cached snapshots, endpoint lists, favourites and recent selections.

Snapshots are stored whole (``catalog_snapshots``); a run records the snapshot id and the exact
model/endpoint metadata it used, so later catalog changes never alter a run's provenance. If the
provider is unreachable, the latest stored snapshot is served and marked stale.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from benchcore.hashing import content_hash

from .context import AppContext
from .db import jdump, jload, now, parse_time, tx
from .providers.base import EndpointInfo, ModelInfo

log = logging.getLogger(__name__)
MAX_RECENTS = 10


def model_from_dict(d: dict[str, Any]) -> ModelInfo:
    return ModelInfo(
        provider=d["provider"], model_id=d["model_id"], name=d["name"], context_length=d.get("context_length"),
        pricing=d.get("pricing") or {}, supported_parameters=list(d.get("supported_parameters") or []),
        reasoning=d.get("reasoning"), max_completion_tokens=d.get("max_completion_tokens"),
        description=d.get("description", ""), input_modalities=list(d.get("input_modalities") or []),
        output_modalities=list(d.get("output_modalities") or []), is_mock=bool(d.get("is_mock")),
    )


def endpoint_from_dict(d: dict[str, Any]) -> EndpointInfo:
    return EndpointInfo(
        slug=d["slug"], provider_name=d.get("provider_name") or "", context_length=d.get("context_length"),
        pricing=d.get("pricing") or {}, supported_parameters=list(d.get("supported_parameters") or []),
        max_completion_tokens=d.get("max_completion_tokens"), quantization=d.get("quantization"),
        status=d.get("status"))


def _latest(conn: sqlite3.Connection, provider: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM catalog_snapshots WHERE provider=? ORDER BY snapshot_id DESC LIMIT 1",
                        (provider,)).fetchone()


def _age_s(ts: str) -> float:
    import datetime as dt

    return (dt.datetime.now(dt.UTC) - parse_time(ts)).total_seconds()


async def refresh(ctx: AppContext, conn: sqlite3.Connection, provider: str) -> int:
    models = await ctx.providers[provider].list_models()
    data = [m.to_dict() for m in models]
    h = content_hash(data)
    prev = _latest(conn, provider)
    with tx(conn):
        cur = conn.execute(
            "INSERT INTO catalog_snapshots(provider, fetched_at, content_hash, model_count, data_json) "
            "VALUES (?,?,?,?,?)", (provider, now(), h, len(data), jdump(data)))
        sid = int(cur.lastrowid or 0)
        # Keep history bounded: drop older snapshots that no run references.
        conn.execute(
            "DELETE FROM catalog_snapshots WHERE provider=? AND snapshot_id NOT IN "
            "(SELECT snapshot_id FROM catalog_snapshots WHERE provider=? ORDER BY snapshot_id DESC LIMIT 5) "
            "AND snapshot_id NOT IN (SELECT catalog_snapshot_id FROM runs WHERE catalog_snapshot_id IS NOT NULL)",
            (provider, provider))
    if prev is not None and prev["content_hash"] == h:
        log.debug("catalog for %s unchanged", provider)
    return sid


async def catalog(ctx: AppContext, conn: sqlite3.Connection, force: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {"models": [], "snapshots": {}, "errors": {}}
    for provider in ctx.providers:
        row = _latest(conn, provider)
        stale = row is None or _age_s(row["fetched_at"]) > ctx.settings.catalog_ttl_s
        if force or stale:
            try:
                await refresh(ctx, conn, provider)
                row = _latest(conn, provider)
            except Exception as exc:  # serve the last snapshot, say so
                log.warning("catalog refresh for %s failed: %s", provider, exc)
                out["errors"][provider] = f"{type(exc).__name__}: {exc}"[:300]
        if row is None:
            continue
        out["snapshots"][provider] = {
            "snapshot_id": row["snapshot_id"], "fetched_at": row["fetched_at"], "model_count": row["model_count"],
            "stale": _age_s(row["fetched_at"]) > ctx.settings.catalog_ttl_s,
        }
        out["models"] += jload(row["data_json"])
    return out


def find_model(conn: sqlite3.Connection, provider: str, model_id: str) -> tuple[ModelInfo, int] | None:
    row = _latest(conn, provider)
    if row is None:
        return None
    for d in jload(row["data_json"]):
        if d["model_id"] == model_id:
            return model_from_dict(d), row["snapshot_id"]
    return None


async def endpoints(ctx: AppContext, conn: sqlite3.Connection, model_id: str,
                    force: bool = False) -> tuple[list[EndpointInfo], str | None]:
    provider = ctx.provider_name_for(model_id)
    row = conn.execute("SELECT * FROM endpoint_snapshots WHERE provider=? AND model_id=? "
                       "ORDER BY snapshot_id DESC LIMIT 1", (provider, model_id)).fetchone()
    if force or row is None or _age_s(row["fetched_at"]) > ctx.settings.catalog_ttl_s:
        try:
            eps = await ctx.provider_for(model_id).list_endpoints(model_id)
            with tx(conn):
                conn.execute("INSERT INTO endpoint_snapshots(provider, model_id, fetched_at, data_json) "
                             "VALUES (?,?,?,?)", (provider, model_id, now(), jdump([e.to_dict() for e in eps])))
            return eps, None
        except Exception as exc:
            if row is None:
                return [], f"{type(exc).__name__}: {exc}"[:300]
            return [endpoint_from_dict(d) for d in jload(row["data_json"])], f"stale: {exc}"[:300]
    return [endpoint_from_dict(d) for d in jload(row["data_json"])], None


# --- favourites and recents ---------------------------------------------------------------------

def get_pref(conn: sqlite3.Connection, key: str, default: Any) -> Any:
    row = conn.execute("SELECT value_json FROM prefs WHERE key=?", (key,)).fetchone()
    return jload(row["value_json"]) if row else default


def set_pref(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute("INSERT INTO prefs(key, value_json) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET "
                 "value_json=excluded.value_json", (key, jdump(value)))


def toggle_favorite(conn: sqlite3.Connection, model_id: str, on: bool) -> list[str]:
    with tx(conn):
        favs = [m for m in get_pref(conn, "favorites", []) if m != model_id]
        if on:
            favs.append(model_id)
        set_pref(conn, "favorites", favs)
    return favs


def push_recent(conn: sqlite3.Connection, model_id: str) -> None:
    rec = [m for m in get_pref(conn, "recents", []) if m != model_id]
    set_pref(conn, "recents", [model_id, *rec][:MAX_RECENTS])
