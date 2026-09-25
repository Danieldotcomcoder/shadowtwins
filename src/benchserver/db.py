"""SQLite persistence: connections, migrations, short transactions and WAL-safe backups.

* WAL journal mode, ``synchronous=NORMAL``, foreign keys on, 10 s busy timeout.
* Every write happens inside a short ``BEGIN IMMEDIATE`` transaction (``tx``), so concurrent
  API and worker processes serialize cleanly instead of failing on lock upgrades.
* Migrations are numbered SQL files applied in order and recorded in ``schema_migrations``;
  they run before any worker starts (the supervisor runs ``migrate`` first).
* Backups use SQLite's online backup API, which produces a consistent snapshot including pages
  still in the WAL. Restores replace the database file while no process holds it open.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Any

BUSY_TIMEOUT_MS = 10_000


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds")


def parse_time(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


def after(seconds: float) -> str:
    return (dt.datetime.now(dt.UTC) + dt.timedelta(seconds=seconds)).isoformat(timespec="milliseconds")


def connect(path: Path | str) -> sqlite3.Connection:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None,
                           check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """A short write transaction that takes the write lock up front."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def _migration_files() -> list[tuple[int, str, str]]:
    out = []
    for entry in resources.files("benchserver.migrations").iterdir():
        name = entry.name
        if name.endswith(".sql") and name[:4].isdigit():
            out.append((int(name[:4]), name, entry.read_text(encoding="utf-8")))
    return sorted(out)


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply pending migrations; returns the names applied."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                 "(version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
    done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    applied = []
    for version, name, sql in _migration_files():
        if version in done:
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            for stmt in _split_sql(sql):
                conn.execute(stmt)
            conn.execute("INSERT INTO schema_migrations(version, name, applied_at) VALUES (?,?,?)",
                         (version, name, now()))
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        applied.append(name)
    return applied


def _split_sql(sql: str) -> list[str]:
    lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def schema_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row[0] or 0)


def latest_migration() -> int:
    return max(v for v, _, _ in _migration_files())


def backup(src_path: Path | str, dest_path: Path | str) -> dict[str, Any]:
    """Consistent online backup (safe while API and worker are running)."""
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    if tmp.exists():
        tmp.unlink()
    src = connect(src_path)
    try:
        out = sqlite3.connect(str(tmp))
        try:
            src.backup(out)
            check = out.execute("PRAGMA integrity_check").fetchone()[0]
            out.execute("PRAGMA journal_mode=DELETE")
        finally:
            out.close()
    finally:
        src.close()
    if check != "ok":
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"backup integrity check failed: {check}")
    tmp.replace(dest)
    return {"path": str(dest), "bytes": dest.stat().st_size, "integrity": check, "created_at": now()}


def restore(backup_path: Path | str, db_path: Path | str) -> dict[str, Any]:
    """Restore a backup into the live database through SQLite's backup API (WAL-aware; no file
    swapping). Stop the API and worker first so nothing writes during the copy."""
    src = Path(backup_path)
    chk = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    try:
        ok = chk.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise RuntimeError(f"backup failed integrity check: {ok}")
        live = connect(db_path)
        try:
            chk.backup(live)
            live_ok = live.execute("PRAGMA integrity_check").fetchone()[0]
            live.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            live.close()
    finally:
        chk.close()
    if live_ok != "ok":
        raise RuntimeError(f"restored database failed integrity check: {live_ok}")
    return {"restored_from": str(src), "db": str(db_path), "integrity": live_ok, "restored_at": now()}


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def jdump(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def jload(s: str | None) -> Any:
    return json.loads(s) if s else None
