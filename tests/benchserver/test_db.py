import sqlite3

import pytest

from benchserver import db, packsync
from benchserver.config import ROOT

from .conftest import create_run, drain, make_ctx, make_settings, q


def test_migrations_are_idempotent(tmp_path):
    conn = db.connect(tmp_path / "m.db")
    assert db.migrate(conn) == ["0001_initial.sql", "0002_retry_base.sql"]
    assert db.migrate(conn) == []
    assert db.schema_version(conn) == db.latest_migration() == 2
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()


def test_pack_sync_is_idempotent_and_refuses_changed_packs(tmp_path):
    conn = db.connect(tmp_path / "p.db")
    db.migrate(conn)
    first = packsync.sync_packs(conn, ROOT / "packs")
    assert set(first["loaded"]) == {"shadowtwins-dev-v1", "shadowtwins-practice-v1", "shadowtwins-ranked-v1"}
    assert first["errors"] == []
    again = packsync.sync_packs(conn, ROOT / "packs")
    assert again["loaded"] == [] and len(again["skipped"]) == 3
    conn.execute("UPDATE packs SET pack_hash='sha256:changed' WHERE pack_id='shadowtwins-ranked-v1'")
    with pytest.raises(packsync.PackConflict):
        packsync.sync_packs(conn, ROOT / "packs")
    n = conn.execute("SELECT COUNT(*) FROM instances WHERE pack_id='shadowtwins-ranked-v1'").fetchone()[0]
    assert n == 30
    conn.close()


def test_tampered_pack_file_is_rejected(tmp_path):
    import shutil

    packs = tmp_path / "packs"
    shutil.copytree(ROOT / "packs" / "shadowtwins-practice-v1", packs / "shadowtwins-practice-v1")
    victim = next((packs / "shadowtwins-practice-v1" / "certificates").glob("*.json"))
    victim.write_text(victim.read_text(encoding="utf-8").replace('"v_star": ', '"v_star":  '), encoding="utf-8")
    conn = db.connect(tmp_path / "t.db")
    db.migrate(conn)
    report = packsync.sync_packs(conn, packs)
    assert report["loaded"] == [] and "file hash" in report["errors"][0]["error"]
    conn.close()


def test_backup_and_restore_roundtrip_with_live_wal(tmp_path):
    ctx = make_ctx(make_settings(tmp_path))
    run_id = create_run(ctx, "mock/optimal")
    drain(ctx)
    holder = ctx.connect()  # keep a reader open so the WAL is not checkpointed away
    holder.execute("SELECT COUNT(*) FROM events").fetchone()
    info = db.backup(ctx.settings.db_path, tmp_path / "backups" / "b1.db")
    assert info["integrity"] == "ok"
    snap = sqlite3.connect(str(tmp_path / "backups" / "b1.db"))
    assert snap.execute("SELECT COUNT(*) FROM evaluations WHERE run_id=?", (run_id,)).fetchone()[0] == 9
    snap.close()
    holder.close()
    # damage the live database, then restore
    conn = ctx.connect()
    conn.execute("DELETE FROM events")
    conn.close()
    db.restore(tmp_path / "backups" / "b1.db", ctx.settings.db_path)
    assert len(q(ctx, "SELECT * FROM events WHERE run_id=?", (run_id,))) > 9
    assert q(ctx, "SELECT state FROM runs WHERE run_id=?", (run_id,))[0]["state"] == "completed"


def test_restore_refuses_corrupt_backup(tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"SQLite format 3\x00" + b"\x00" * 200)
    with pytest.raises(Exception):  # noqa: B017 - sqlite raises DatabaseError subclasses
        db.restore(bad, tmp_path / "live.db")
