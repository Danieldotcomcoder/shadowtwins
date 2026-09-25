"""P2 pipeline: development scan/report and pack building.

    uv run --extra research python tools/p2_pipeline.py dev-scan --n 400 --jobs 12
    uv run --extra research python tools/p2_pipeline.py dev-report
    uv run --extra research python tools/p2_pipeline.py build --jobs 12
    uv run shadowtwins-verify --jobs 12 packs/shadowtwins-practice-v1 packs/shadowtwins-ranked-v1

``dev-scan`` measures every candidate in the development seed range (no filtering) so admission
thresholds can be chosen from observed distributions. ``build`` requires the frozen policy and
writes the development, practice and ranked packs in that order, sharing one duplicate-geometry set.
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shadowtwins.packs import build_pack, development_scan  # noqa: E402
from shadowtwins.policy import ADMISSION, TIERS, policy_document  # noqa: E402

SCAN = ROOT / "docs" / "reports" / "data" / "dev_scan_v1.jsonl.gz"
REPORT = ROOT / "docs" / "reports" / "DEV_POOL_REPORT.md"
PACKS = ROOT / "packs"


def cmd_dev_scan(args: argparse.Namespace) -> None:
    t0 = time.perf_counter()
    rows = development_scan(args.n, jobs=args.jobs)
    SCAN.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(SCAN, "wt", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    print(f"scanned {len(rows)} candidates in {time.perf_counter() - t0:.1f}s -> {SCAN}")


def _q(vals: list[float]) -> str:
    if not vals:
        return "—"
    v = sorted(vals)
    n = len(v)

    def at(p: float) -> float:
        return v[min(n - 1, int(p * (n - 1) + 0.5))]

    return f"{at(0):.3g} / {at(0.25):.3g} / {at(0.5):.3g} / {at(0.75):.3g} / {at(1):.3g}"


def cmd_dev_report(args: argparse.Namespace) -> None:
    with gzip.open(SCAN, "rt", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    out: list[str] = []
    w = out.append
    w("# Development pool report (st-gen-1.0.0)\n")
    w("Every candidate in the development seed range was generated, certified exhaustively and "
      "measured, with no filtering. Practice and ranked seed ranges were **not** generated before "
      "the admission policy below was frozen. No model was run.\n")
    w(f"Source data: `docs/reports/data/{SCAN.name}` ({len(rows)} candidates). "
      "Reproduce: `uv run --extra research python tools/p2_pipeline.py dev-scan --n 400` then "
      "`dev-report`.\n")
    w("Quantiles are min / q1 / median / q3 / max.\n")
    for tier in TIERS:
        rs = [r for r in rows if r["budget"] == tier.budget]
        meas = [r["metrics"] for r in rs if r["status"] == "measured"]
        st = Counter(r["status"] for r in rs)
        w(f"\n## Budget {tier.budget} (candidates for {tier.id}, {tier.name})\n")
        w(f"* Candidates: {len(rs)}; structurally invalid draws: {st['structurally_invalid']}; "
          f"`v* = 0`: {st['zero_optimum']}; `v* > 0`: {len(meas)}")
        adm = [r for r in rs if r["status"] == "measured" and not r["admission_failures"]]
        tier_ok = [r for r in adm if r["tier_match"]]
        w(f"* Admitted under the frozen policy: {len(adm)} ({len(adm) / len(rs):.1%} of candidates); "
          f"also matching the {tier.id} rule: {len(tier_ok)} ({len(tier_ok) / len(rs):.1%})")
        fails = Counter(f for r in rs if r["status"] == "measured" for f in r["admission_failures"])
        w("* Admission failures among `v* > 0` (a candidate can fail several): "
          + ", ".join(f"`{k}` {v}" for k, v in fails.most_common()))
        w(f"* Shadow constraint binding (no-shadow optimum > v*): "
          f"{sum(m['shadow_binding'] for m in meas)} of {len(meas)}; with at least one shadow trap: "
          f"{sum(1 for m in meas if m['shadow_traps'] > 0)} of {len(meas)}")
        mm = Counter(m["min_moves_for_optimum"] for m in meas)
        w("* Minimum relocations needed for the optimum: "
          + ", ".join(f"{k}: {mm[k]}" for k in sorted(mm)))
        w(f"* Local search reaches the optimum: {sum(1 for m in meas if m['local_search_score'] >= 100)}"
          f" of {len(meas)}\n")
        w("| metric (v* > 0) | min / q1 / median / q3 / max | admitted |")
        w("|---|---|---|")
        am = [r["metrics"] for r in adm]
        for key, label in [
            ("v_star", "v*"), ("pairs", "entrance pairs"),
            ("legal_density", "legal density"), ("optimum_density", "optimum density"),
            ("shadow_rejection_rate", "shadow rejection rate"), ("shadow_traps", "shadow traps"),
            ("random_legal_expected_score", "random legal expected score"),
            ("random_candidate_expected_score", "random candidate expected score"),
            ("local_search_score", "local search score"), ("tokens_max", "prompt tokens (panel max)"),
            ("certify_ms", "certification ms"),
        ]:
            w(f"| {label} | {_q([m[key] for m in meas])} | {_q([m[key] for m in am])} |")
        pl = Counter(len(m["partial_levels"]) for m in meas)
        w("\nPartial-credit levels strictly between 0 and v*: "
          + ", ".join(f"{k}: {pl[k]}" for k in sorted(pl)) + "\n")
    all_meas = [r["metrics"] for r in rows if r["status"] == "measured"]
    w("\n## Shadow activity across the pool\n")
    rej = [m["shadow_rejection_rate"] for m in all_meas]
    w(f"Across {len(all_meas)} candidates with `v* > 0`, the silhouette rule rejected a median "
      f"{statistics.median(rej):.1%} of otherwise permitted edits; "
      f"{sum(1 for x in rej if x < ADMISSION.min_shadow_rejection_rate)} candidates fell below the "
      f"{ADMISSION.min_shadow_rejection_rate:.0%} activity floor and are excluded as "
      "shell-protected or shadow-irrelevant. Shadow preservation is therefore an active constraint "
      "in the admitted population, not a vacuous one.\n")
    w("\n## Frozen policy\n")
    w("```json\n" + json.dumps(policy_document(), indent=2) + "\n```\n")
    REPORT.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {REPORT}")


def cmd_build(args: argparse.Namespace) -> None:
    used: set[str] = set()
    for pack_id, split in [("shadowtwins-dev-v1", "development"),
                           ("shadowtwins-practice-v1", "practice"),
                           ("shadowtwins-ranked-v1", "ranked")]:
        if (PACKS / pack_id / "manifest.json").exists() and not args.force:
            raise SystemExit(f"{pack_id} exists and packs are immutable; refusing to overwrite")
        t0 = time.perf_counter()
        m = build_pack(pack_id, split, PACKS, used, jobs=args.jobs)
        print(f"{pack_id}: {len(m['items'])} instances, token max {m['token_report']['max']}, "
              f"pack_hash {m['pack_hash']} ({time.perf_counter() - t0:.1f}s)")
        for tid, st in m["selection_stats"].items():
            print(f"   {tid}: {st}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("dev-scan")
    p.add_argument("--n", type=int, default=400)
    p.add_argument("--jobs", type=int, default=8)
    p.set_defaults(fn=cmd_dev_scan)
    p = sub.add_parser("dev-report")
    p.set_defaults(fn=cmd_dev_report)
    p = sub.add_parser("build")
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--force", action="store_true", help="development only: overwrite existing packs")
    p.set_defaults(fn=cmd_build)
    args = ap.parse_args(argv)
    args.fn(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
