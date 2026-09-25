"""``shadowtwins-verify``: reproduce certificates without any LLM call or engine code.

Usage:
    shadowtwins-verify PACK_DIR [PACK_DIR ...]          # directory with manifest.json
    shadowtwins-verify --instance I.json --certificate C.json
    shadowtwins-verify --jobs 8 --report out.json PACK_DIR

Pack directories must contain ``manifest.json`` listing ``items`` with ``instance`` and
``certificate`` paths (relative to the pack) and their file hashes. Exit status is 0 only when every
certificate reproduces exactly and every listed file hash matches.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from .core import VERIFIER_VERSION, compare_certificate


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_pair(args: tuple[str, str]) -> dict[str, Any]:
    inst_path, cert_path = args
    t0 = time.perf_counter()
    try:
        instance = json.loads(Path(inst_path).read_text(encoding="utf-8"))
        certificate = json.loads(Path(cert_path).read_text(encoding="utf-8"))
        result = compare_certificate(instance, certificate)
        mismatches = result["mismatches"]
        instance_id = instance.get("instance_id")
    except Exception as exc:  # report, never crash the whole batch
        mismatches = [f"error: {type(exc).__name__}: {exc}"]
        instance_id = None
    return {
        "instance": inst_path,
        "certificate": cert_path,
        "instance_id": instance_id,
        "status": "verified" if not mismatches else "mismatch",
        "mismatches": mismatches,
        "runtime_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


def _pack_pairs(pack: Path) -> tuple[list[tuple[str, str]], list[str]]:
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    problems: list[str] = []
    pairs: list[tuple[str, str]] = []
    for item in manifest["items"]:
        ip, cp = pack / item["instance"], pack / item["certificate"]
        for path, key in ((ip, "instance_file_hash"), (cp, "certificate_file_hash")):
            if key in item and _file_hash(path) != item[key]:
                problems.append(f"{path}: file hash differs from manifest {key}")
        pairs.append((str(ip), str(cp)))
    return pairs, problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="shadowtwins-verify", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("packs", nargs="*", type=Path, help="pack directories containing manifest.json")
    ap.add_argument("--instance", type=Path)
    ap.add_argument("--certificate", type=Path)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--report", type=Path, help="write a JSON report here")
    args = ap.parse_args(argv)

    pairs: list[tuple[str, str]] = []
    problems: list[str] = []
    if args.instance or args.certificate:
        if not (args.instance and args.certificate):
            ap.error("--instance and --certificate must be given together")
        pairs.append((str(args.instance), str(args.certificate)))
    for pack in args.packs:
        p, pr = _pack_pairs(pack)
        pairs += p
        problems += pr
    if not pairs:
        ap.error("nothing to verify")

    t0 = time.perf_counter()
    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            results = list(ex.map(_verify_pair, pairs))
    else:
        results = [_verify_pair(pair) for pair in pairs]
    failed = [r for r in results if r["status"] != "verified"]
    for r in results:
        mark = "OK " if r["status"] == "verified" else "BAD"
        print(f"{mark} {r['instance_id']} ({r['runtime_ms']} ms)")
        for m in r["mismatches"]:
            print(f"    - {m}")
    for pr in problems:
        print(f"BAD {pr}")
    summary = {
        "verifier_version": VERIFIER_VERSION,
        "checked": len(results),
        "verified": len(results) - len(failed),
        "failed": len(failed),
        "file_hash_problems": problems,
        "runtime_s": round(time.perf_counter() - t0, 2),
        "results": results,
    }
    print(f"{summary['verified']}/{summary['checked']} certificates reproduced; "
          f"{len(problems)} file-hash problems; {summary['runtime_s']} s")
    if args.report:
        args.report.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0 if not failed and not problems else 1


if __name__ == "__main__":
    sys.exit(main())
