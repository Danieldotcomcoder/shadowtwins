from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from benchcore.contracts import RunMode, RunSpec
from benchserver import db, runs
from benchserver.app_state import prepare_database
from benchserver.config import ROOT, RetryPolicy, load_settings
from benchserver.context import AppContext
from benchserver.providers.mock import MockProvider
from benchserver.worker import Worker


def make_settings(tmp_path: Path, **kw: Any):
    base: dict[str, Any] = dict(
        data_dir=tmp_path, db_path=tmp_path / "test.db", packs_dir=ROOT / "packs",
        frontend_dist=tmp_path / "no-dist", enable_mock_provider=True, auth_mode="open",
        operator_token=None, openrouter_api_key=None, poll_s=0.02, heartbeat_s=0.2, lease_ttl_s=5.0,
        worker_stale_after_s=5.0, retry=RetryPolicy(max_attempts=4, base_delay_s=0.01, max_delay_s=0.05),
    )
    base.update(kw)
    return load_settings(**base)


def make_ctx(settings) -> AppContext:
    prepare_database(settings)
    ctx = AppContext(settings, providers={})
    ctx.providers["mock"] = MockProvider(ctx.answer_book, slow_delay_s=0.3)
    return ctx


@pytest.fixture
def ctx(tmp_path: Path) -> AppContext:
    return make_ctx(make_settings(tmp_path))


def create_run(ctx: AppContext, model_id: str, mode: RunMode = RunMode.QUICK_CHECK, limit: float = 5.0,
               concurrency: int = 4, endpoint: str | None = None, allow_unknown: bool = False) -> str:
    conn = ctx.connect()
    try:
        spec = RunSpec(model_id=model_id, provider=endpoint, profile_id="standard", mode=mode,
                       spend_limit_usd=limit, concurrency=concurrency, allow_unknown_pricing=allow_unknown)
        return asyncio.run(runs.create(ctx, conn, spec))
    finally:
        conn.close()


def drain(ctx: AppContext, idle_s: float = 0.25, worker_id: str | None = None) -> Worker:
    """Run a worker until nothing is dispatchable for ``idle_s``."""
    w = Worker(ctx, worker_id)
    asyncio.run(w.run(idle_exit_s=idle_s))
    return w


class BackgroundWorker:
    """A worker on its own thread and event loop, for tests that control runs mid-flight."""

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._stop = threading.Event()
        self.worker: Worker | None = None
        self.thread = threading.Thread(target=self._main, daemon=True)

    def _main(self) -> None:
        async def go() -> None:
            stop = asyncio.Event()
            self.worker = Worker(self.ctx)

            async def watch() -> None:
                while not self._stop.is_set():
                    await asyncio.sleep(0.02)
                stop.set()

            watcher = asyncio.create_task(watch())
            await self.worker.run(stop)
            await watcher

        asyncio.run(go())

    def __enter__(self) -> BackgroundWorker:
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self.thread.join(timeout=30)


def wait_for(pred, timeout: float = 15.0, step: float = 0.02) -> None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if pred():
            return
        time.sleep(step)
    raise AssertionError("condition not met in time")


def q(ctx: AppContext, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    conn = ctx.connect()
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def summary(ctx: AppContext, run_id: str) -> dict[str, Any]:
    conn = ctx.connect()
    try:
        return runs.summary(conn, run_id)
    finally:
        conn.close()


__all__ = ["BackgroundWorker", "create_run", "db", "drain", "make_ctx", "make_settings", "q", "summary", "wait_for"]
