"""Release acceptance matrix (P5). Records actual results; never marks unavailable checks as passed.

    uv run --extra research python tools/release_check.py            # core gates
    uv run --extra research python tools/release_check.py --frontend # + vitest, build, Playwright e2e

Writes docs/reports/RELEASE_CHECK.md and .json. Container gates come from
docs/reports/CONTAINER_ACCEPTANCE.json (tools/container_acceptance.py). The live pilot gate is
reported BLOCKED unless OPENROUTER_API_KEY and a spending cap were used by tools/pilot.py.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

Gate = dict[str, Any]


def run(cmd: list[str], cwd: Path = ROOT, timeout: float = 1800) -> tuple[int, str]:
    shell = os.name == "nt" and cmd[0] in ("pnpm",)
    p = subprocess.run(cmd if not shell else " ".join(cmd), cwd=cwd, capture_output=True, text=True,
                       timeout=timeout, encoding="utf-8", errors="replace", shell=shell)
    return p.returncode, (p.stdout + p.stderr)


def last_line(text: str, pattern: str) -> str:
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)  # strip ANSI colours
    hits = [ln.strip() for ln in text.splitlines() if re.search(pattern, ln)]
    return hits[-1] if hits else text.strip().splitlines()[-1][:200] if text.strip() else ""


def gate_cmd(name: str, cmd: list[str], pattern: str, cwd: Path = ROOT) -> Gate:
    t0 = time.monotonic()
    code, out = run(cmd, cwd)
    return {"gate": name, "status": "pass" if code == 0 else "fail", "evidence": last_line(out, pattern),
            "command": " ".join(cmd), "seconds": round(time.monotonic() - t0, 1)}


def token_recount() -> Gate:
    from benchcore.packs import load_pack
    from shadowtwins.prompt import render_prompt
    from shadowtwins.tokens import CEILING, PANEL_VERSION, count_messages

    worst, checked, mismatches = 0, 0, []
    for pack in ("shadowtwins-practice-v1", "shadowtwins-ranked-v1"):
        loaded = load_pack(ROOT / "packs" / pack)
        for item in loaded.items:
            report = count_messages(render_prompt(item.instance).messages)  # type: ignore[arg-type]
            checked += 1
            worst = max(worst, report["max"])
            if report["max"] != item.tokens_max:
                mismatches.append(item.instance_id)
    ok = not mismatches and worst <= CEILING
    return {"gate": "token ceiling re-measured under the frozen panel", "status": "pass" if ok else "fail",
            "evidence": f"{checked} practice+ranked prompts re-rendered; panel {PANEL_VERSION} max {worst} ≤ {CEILING}; "
                        f"{len(mismatches)} differ from manifests", "command": "tools/release_check.py (token_recount)"}


def end_to_end_consistency() -> Gate:
    """Full runner path with the mock provider, then independent checks of scores and replays."""
    from benchcore.aggregate import ScoredItem, aggregate
    from benchcore.contracts import RunMode, RunSpec
    from benchserver import exports, runs
    from benchserver.app_state import prepare_database
    from benchserver.config import RetryPolicy, load_settings
    from benchserver.context import AppContext
    from benchserver.providers.mock import MockProvider
    from benchserver.worker import Worker
    from stverify.core import Puzzle, evaluate_answer, linked_pairs, shadows

    t0 = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        settings = load_settings(data_dir=Path(tmp), db_path=Path(tmp) / "rc.db", packs_dir=ROOT / "packs",
                                 frontend_dist=Path(tmp) / "none", enable_mock_provider=True, auth_mode="open",
                                 poll_s=0.02, retry=RetryPolicy(base_delay_s=0.01, max_delay_s=0.05))
        prepare_database(settings)
        ctx = AppContext(settings, providers={})
        ctx.providers["mock"] = MockProvider(ctx.answer_book)
        conn = ctx.connect()
        spec = RunSpec(model_id="mock/random", profile_id="standard", mode=RunMode.STANDARD, spend_limit_usd=5,
                       concurrency=8)
        run_id = asyncio.run(runs.create(ctx, conn, spec))
        asyncio.run(Worker(ctx).run(idle_exit_s=0.3))
        summary = runs.summary(conn, run_id)
        re_eval = exports.reevaluate(ctx, conn, run_id)
        rows = exports.export_csv(conn, run_id).splitlines()
        import csv

        items = [ScoredItem(r["instance_id"], r["tier"], int(r["repetition"]), r["job_state"], float(r["score"]),
                            r["valid"] == "1") for r in csv.DictReader(rows)]
        offline = aggregate(items)
        replay_checks = 0
        problems: list[str] = []
        for job in conn.execute("SELECT job_id, instance_id, evaluation_id FROM jobs WHERE run_id=?", (run_id,)):
            module, inst, cert, _ = ctx.load_item(conn, job["instance_id"])
            env = exports.jload(conn.execute("SELECT envelope_json FROM evaluations WHERE evaluation_id=?",
                                             (job["evaluation_id"],)).fetchone()["envelope_json"])
            from benchcore.contracts import EvaluationEnvelope

            rep = module.build_replay(inst, cert, EvaluationEnvelope.model_validate(env)).model_dump(mode="json")
            puzzle = Puzzle(inst.model_dump(mode="json"))
            edit = env["detail"]["edit"]
            if edit is not None:
                indep = evaluate_answer(puzzle, edit["remove"], edit["add"])
                if indep["valid"] != env["valid"] or (env["valid"] and indep["objective"] != env["raw_objective"]):
                    problems.append(f"{job['instance_id']}: independent verdict differs")
            for label in ("original", "optimal", "model"):
                state = rep["original"] if label == "original" else (rep[label] or {}).get("final")
                if not state:
                    continue
                solid = {(i % 4, (i // 4) % 4, i // 16) for i, ch in enumerate(state["occupancy"]) if ch == "1"}
                sx, sy, sz = shadows(solid)
                drawn = [{(u, v) for v in range(4) for u in range(4) if state["silhouettes"][ax][v][u]} for ax in "xyz"]
                if drawn != [set(sx), set(sy), set(sz)]:
                    problems.append(f"{job['instance_id']}/{label}: silhouettes differ from verifier")
                comp = state["entrance_component"]
                from_comp = {(i, j) for i in range(len(comp)) for j in range(i + 1, len(comp)) if comp[i] != -1 and comp[i] == comp[j]}
                if from_comp != linked_pairs(solid, puzzle.entrances):
                    problems.append(f"{job['instance_id']}/{label}: connectivity differs from verifier")
                replay_checks += 1
        conn.close()
    ok = (summary["state"] == "completed" and not re_eval["mismatches"] and re_eval["aggregate_matches"]
          and offline["overall"] == summary["scores"]["overall"] and not problems)
    return {"gate": "offline score recomputation and UI replay consistency (independent verifier)",
            "status": "pass" if ok else "fail",
            "evidence": f"mock/random standard run: {summary['scores']['completed']}/30 evaluated, overall "
                        f"{summary['scores']['overall']:.4f}; re-evaluation mismatches {len(re_eval['mismatches'])}; CSV "
                        f"recomputation equal: {offline['overall'] == summary['scores']['overall']}; {replay_checks} replay "
                        f"states checked against stverify, {len(problems)} problems",
            "command": "tools/release_check.py (end_to_end_consistency)", "seconds": round(time.monotonic() - t0, 1)}


def container_gates() -> list[Gate]:
    path = ROOT / "docs" / "reports" / "CONTAINER_ACCEPTANCE.json"
    if not path.exists():
        return [{"gate": "single-container release", "status": "not_run",
                 "evidence": "run tools/container_acceptance.py with Docker", "command": ""}]
    rep = json.loads(path.read_text(encoding="utf-8"))
    return [{"gate": f"container: {r['gate']}", "status": r["status"], "evidence": r["detail"],
             "command": "tools/container_acceptance.py"} for r in rep["results"]]


def pilot_gate() -> Gate:
    path = ROOT / "docs" / "research" / "pilot_results.json"
    if path.exists():
        rep = json.loads(path.read_text(encoding="utf-8"))
        ok = rep.get("completed_models", 0) >= 2 and rep.get("within_cap")
        return {"gate": "live pilot (small + larger model, explicit cap)", "status": "pass" if ok else "fail",
                "evidence": rep.get("summary", ""), "command": "tools/pilot.py"}
    reason = ("OPENROUTER_API_KEY is not set in this environment" if not os.environ.get("OPENROUTER_API_KEY")
              else "tools/pilot.py has not been run with an explicit --cap")
    return {"gate": "live pilot (small + larger model, explicit cap)", "status": "blocked", "evidence": reason,
            "command": "OPENROUTER_API_KEY=... uv run python tools/pilot.py --cap 2.00 --yes"}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    frontend = "--frontend" in sys.argv
    uv = ["uv", "run", "--extra", "research"]
    gates: list[Gate] = [
        gate_cmd("python lint (ruff)", [*uv, "ruff", "check", "src", "tests", "tools"], r"All checks|error"),
        gate_cmd("python types (pyright)", [*uv, "pyright"], r"errors"),
        gate_cmd("python test suite", [*uv, "pytest", "-q", "-o", "addopts=", "-p", "no:warnings"], r"passed|failed"),
        gate_cmd("benchmark contracts unchanged", [*uv, "shadowtwins", "export-contracts", "--check"], r"contract"),
        gate_cmd("API contract unchanged", [*uv, "benchserver", "export-openapi", "--check"], r"openapi"),
        gate_cmd("every ranked/practice/dev certificate independently reproduced",
                 [*uv, "shadowtwins-verify", "--jobs", "8", "packs/shadowtwins-ranked-v1", "packs/shadowtwins-practice-v1",
                  "packs/shadowtwins-dev-v1"], r"certificates reproduced"),
    ]
    gates.append(token_recount())
    gates.append(end_to_end_consistency())
    if frontend:
        fe = ROOT / "frontend"
        gates.append(gate_cmd("frontend unit tests (fixture cross-checks, contract drift)", ["pnpm", "test"], r"Tests", fe))
        gates.append(gate_cmd("frontend production build", ["pnpm", "build"], r"built in|error", fe))
        gates.append(gate_cmd("frontend end-to-end + accessibility (Playwright, axe)", ["pnpm", "e2e"], r"passed|failed", fe))
    gates += container_gates()
    gates.append(pilot_gate())
    for g in gates:
        print(f"{g['status'].upper():8} {g['gate']}: {g['evidence']}")
    counts = {s: sum(1 for g in gates if g["status"] == s) for s in ("pass", "fail", "blocked", "not_run")}
    out = ROOT / "docs" / "reports"
    (out / "RELEASE_CHECK.json").write_text(json.dumps({"counts": counts, "gates": gates}, indent=2), encoding="utf-8")
    icon = {"pass": "✅ pass", "fail": "❌ fail", "blocked": "⛔ blocked", "not_run": "⏸ not run"}
    lines = ["# Release acceptance matrix", "",
             f"Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} by `tools/release_check.py"
             f"{' --frontend' if frontend else ''}` (container rows from `tools/container_acceptance.py`).", "",
             f"**{counts['pass']} pass · {counts['fail']} fail · {counts['blocked']} blocked · {counts['not_run']} not run.**",
             "", "| Gate | Result | Evidence |", "|---|---|---|"]
    lines += [f"| {g['gate']} | {icon[g['status']]} | {g['evidence']} |" for g in gates]
    (out / "RELEASE_CHECK.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if counts["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
