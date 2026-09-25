"""Benchmark-agnostic pack loading.

A pack directory contains ``manifest.json`` with ``pack_id``, ``benchmark_id``, ``split``,
``ranked``, ``pack_hash``, ``policy_hash``, ``versions`` and ordered ``items`` (``instance_id``,
``tier``, ``order``, ``content_hash``, ``certificate_core_hash``, ``v_star`` / ``max_objective``,
``instance``/``certificate`` paths and file hashes). Every file hash is checked and every document
is parsed through the owning benchmark module, which re-checks its own content hashes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from . import registry
from .hashing import sha256_file


@dataclass
class PackItem:
    instance_id: str
    tier: str
    order: int
    content_hash: str
    certificate_hash: str
    max_objective: int
    tokens_max: int | None
    verified: bool
    instance: BaseModel
    certificate: BaseModel
    instance_doc: dict[str, Any]
    certificate_doc: dict[str, Any]


@dataclass
class LoadedPack:
    manifest: dict[str, Any]
    items: list[PackItem]

    @property
    def pack_id(self) -> str:
        return self.manifest["pack_id"]


class PackIntegrityError(ValueError):
    pass


def load_pack(pack_dir: Path) -> LoadedPack:
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    module = registry.get(manifest["benchmark_id"])
    items: list[PackItem] = []
    for it in manifest["items"]:
        ip, cp = pack_dir / it["instance"], pack_dir / it["certificate"]
        for path, key in ((ip, "instance_file_hash"), (cp, "certificate_file_hash")):
            if sha256_file(str(path)) != it[key]:
                raise PackIntegrityError(f"{path}: file hash differs from manifest")
        idoc = json.loads(ip.read_text(encoding="utf-8"))
        cdoc = json.loads(cp.read_text(encoding="utf-8"))
        inst = module.load_instance(idoc)
        cert = module.load_certificate(cdoc)
        if idoc.get("content_hash") != it["content_hash"] or cdoc.get("core_hash") != it["certificate_core_hash"]:
            raise PackIntegrityError(f"{it['instance_id']}: identity hash differs from manifest")
        verified = cdoc.get("independent_verification", {}).get("status") == "verified"
        items.append(PackItem(
            instance_id=it["instance_id"], tier=it["tier"], order=it["order"],
            content_hash=it["content_hash"], certificate_hash=it["certificate_core_hash"],
            max_objective=int(it.get("max_objective", it.get("v_star"))),
            tokens_max=it.get("tokens_max"), verified=verified,
            instance=inst, certificate=cert, instance_doc=idoc, certificate_doc=cdoc,
        ))
    if manifest.get("ranked") and not all(i.verified for i in items):
        raise PackIntegrityError(f"{manifest['pack_id']}: ranked pack has unverified certificates")
    return LoadedPack(manifest=manifest, items=items)


def discover(packs_dir: Path) -> list[Path]:
    if not packs_dir.exists():
        return []
    return sorted(p for p in packs_dir.iterdir() if (p / "manifest.json").exists())
