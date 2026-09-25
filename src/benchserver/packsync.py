"""Load shipped packs into the database (idempotent; never recertifies at startup).

A pack already present with the same ``pack_hash`` is skipped. A pack id that reappears with a
different hash is refused: packs are immutable and corrections must use a new pack id.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from benchcore.packs import discover, load_pack

from .db import jdump, now, tx

log = logging.getLogger(__name__)


class PackConflict(RuntimeError):
    pass


def sync_packs(conn: sqlite3.Connection, packs_dir: Path) -> dict[str, Any]:
    report: dict[str, Any] = {"loaded": [], "skipped": [], "errors": []}
    for d in discover(packs_dir):
        try:
            pack = load_pack(d)
        except Exception as exc:  # integrity failures must be visible, not fatal to other packs
            log.error("pack %s failed integrity checks: %s", d.name, exc)
            report["errors"].append({"pack": d.name, "error": str(exc)})
            continue
        m = pack.manifest
        existing = conn.execute("SELECT pack_hash FROM packs WHERE pack_id=?", (m["pack_id"],)).fetchone()
        if existing is not None:
            if existing["pack_hash"] != m["pack_hash"]:
                raise PackConflict(f"pack {m['pack_id']} changed on disk (hash {m['pack_hash']} != "
                                   f"stored {existing['pack_hash']}); packs are immutable")
            report["skipped"].append(m["pack_id"])
            continue
        with tx(conn):
            conn.execute(
                "INSERT INTO packs(pack_id, benchmark_id, split, ranked, pack_hash, policy_hash, "
                "versions_json, manifest_json, loaded_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (m["pack_id"], m["benchmark_id"], m["split"], int(bool(m.get("ranked"))), m["pack_hash"],
                 m.get("policy_hash"), jdump(m.get("versions", {})), jdump(m), now()))
            for it in pack.items:
                conn.execute(
                    "INSERT INTO instances(instance_id, benchmark_id, pack_id, tier, ord, content_hash, "
                    "tokens_max, instance_json) VALUES (?,?,?,?,?,?,?,?)",
                    (it.instance_id, m["benchmark_id"], m["pack_id"], it.tier, it.order, it.content_hash,
                     it.tokens_max, jdump(it.instance_doc)))
                conn.execute(
                    "INSERT INTO certificates(instance_id, core_hash, max_objective, verified, "
                    "certificate_json) VALUES (?,?,?,?,?)",
                    (it.instance_id, it.certificate_hash, it.max_objective, int(it.verified),
                     jdump(it.certificate_doc)))
        report["loaded"].append(m["pack_id"])
    return report
