"""Bounded research pilot (P5): one small and one larger model on the frozen ranked pack.

    OPENROUTER_API_KEY=... uv run python tools/pilot.py --cap 2.00            # plan only, sends nothing
    OPENROUTER_API_KEY=... uv run python tools/pilot.py --cap 2.00 --yes      # run the pilot
    uv run python tools/pilot.py --dry-run-mock --yes                         # tooling check with mock models

Rules (docs/research/STUDY_PROTOCOL.md): the Standard track of `shadowtwins-ranked-v1`, profile
`standard`, a pinned endpoint per model, and an explicit total spending cap split evenly between
the two runs. Nothing is sent without --yes, and a run whose worst case exceeds its share of the cap
is refused (so a completed pilot never silently stops at the budget). The frozen pack is never
modified after results are seen. Prespecified analyses are labelled as such; anything else is
exploratory.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from benchcore.aggregate import BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED  # noqa: E402
from benchcore.contracts import RunMode, RunSpec  # noqa: E402
from benchserver import catalog, runs  # noqa: E402
from benchserver.app_state import prepare_database  # noqa: E402
from benchserver.config import load_settings  # noqa: E402
from benchserver.context import AppContext  # noqa: E402
from benchserver.costs import prompt_estimate  # noqa: E402
from benchserver.profiles import PROFILE_BY_ID, compatibility  # noqa: E402
from benchserver.providers.mock import MockProvider  # noqa: E402
from benchserver.worker import Worker  # noqa: E402

DEFAULT_SMALL = "meta-llama/llama-3.1-8b-instruct"
DEFAULT_LARGE = "meta-llama/llama-3.3-70b-instruct"
RANKED = "shadowtwins-ranked-v1"


async def pick_endpoint(ctx: AppContext, conn: Any, model_id: str, explicit: str | None) -> str:
    await catalog.catalog(ctx, conn)  # make sure a catalog snapshot exists
    eps, err = await catalog.endpoints(ctx, conn, model_id, force=True)
    if explicit:
        if not any(e.slug == explicit for e in eps):
            raise SystemExit(f"endpoint {explicit} not listed for {model_id}: {[e.slug for e in eps]}")
        return explicit
    found = catalog.find_model(conn, ctx.provider_name_for(model_id), model_id)
    if found is None:
        raise SystemExit(f"{model_id} not in catalog")
    model = found[0]
    pt = prompt_estimate(max(r[0] or 800 for r in conn.execute("SELECT tokens_max FROM instances")))
    usable = [e for e in eps if compatibility(model, PROFILE_BY_ID["standard"], pt, e)["compatible"]
              and e.pricing.get("prompt") is not None and e.pricing.get("completion") is not None]
    if not usable:
        raise SystemExit(f"no compatible priced endpoint for {model_id} ({err or 'none listed'})")
    usable.sort(key=lambda e: (e.pricing["prompt"] or 0) * 900 + (e.pricing["completion"] or 0) * 1500)
    return usable[0].slug


def instance_scores(conn: Any, run_id: str) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for r in conn.execute("SELECT j.tier, j.instance_id, e.score FROM jobs j JOIN evaluations e "
                          "ON e.evaluation_id=j.evaluation_id WHERE j.run_id=?", (run_id,)):
        out.setdefault(r["tier"], {})[r["instance_id"]] = r["score"]
    return out


def h1_contrast(scores: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Prespecified H1: T1 mean - mean(T2, T3), stratified bootstrap over instances."""
    def stat(s: dict[str, list[float]]) -> float:
        m = {t: statistics.fmean(v) for t, v in s.items()}
        return m["T1"] - (m["T2"] + m["T3"]) / 2

    tiers = {t: list(v.values()) for t, v in scores.items()}
    if not all(t in tiers for t in ("T1", "T2", "T3")):
        return {"estimate": None}
    rng = random.Random(BOOTSTRAP_SEED)
    boot = sorted(stat({t: [v[rng.randrange(len(v))] for _ in v] for t, v in tiers.items()})
                  for _ in range(BOOTSTRAP_RESAMPLES))
    lo, hi = boot[int(0.025 * (len(boot) - 1) + 0.5)], boot[int(0.975 * (len(boot) - 1) + 0.5)]
    return {"estimate": stat(tiers), "interval_95": [lo, hi], "direction_predicted": "positive"}


def shadow_association(conn: Any, run_id: str) -> dict[str, Any]:
    """Prespecified H2 (part): correlation between answer validity and shadow rejection rate."""
    rates = {}
    for row in json.loads((ROOT / "packs" / RANKED / "reports" / "metrics.json").read_text(encoding="utf-8")):
        rates[row["instance_id"]] = row["metrics"]["shadow_rejection_rate"]
    pts = [(rates[r["instance_id"]], float(r["valid"])) for r in conn.execute(
        "SELECT instance_id, valid FROM evaluations WHERE run_id=?", (run_id,))]
    if len(pts) < 3 or len({v for _, v in pts}) < 2:
        return {"correlation": None, "n": len(pts), "note": "validity is constant; correlation undefined"}
    xs, ys = zip(*pts, strict=True)
    return {"correlation": statistics.correlation(xs, ys), "n": len(pts)}


async def main_async(args: argparse.Namespace) -> int:
    mock = args.dry_run_mock
    data_dir = ROOT / "data" / ("pilot-dry-run" if mock else "pilot")
    settings = load_settings(data_dir=data_dir, db_path=data_dir / "pilot.db", enable_mock_provider=mock)
    if not mock and not settings.openrouter_configured:
        print("OPENROUTER_API_KEY is not set: the live pilot cannot run. (Use --dry-run-mock to check tooling.)")
        return 2
    if not mock and args.cap is None:
        print("An explicit --cap (USD, total for both models) is required.")
        return 2
    cap = args.cap if args.cap is not None else 1.0
    prepare_database(settings)
    ctx = AppContext(settings)
    if mock:
        ctx.providers = {"mock": MockProvider(ctx.answer_book)}
    conn = ctx.connect()
    models = [("small", args.small or ("mock/random" if mock else DEFAULT_SMALL), args.small_endpoint),
              ("larger", args.large or ("mock/optimal" if mock else DEFAULT_LARGE), args.large_endpoint)]
    plans = []
    for role, model_id, ep in models:
        endpoint = await pick_endpoint(ctx, conn, model_id, ep)
        spec = RunSpec(model_id=model_id, provider=endpoint, profile_id="standard", mode=RunMode.STANDARD,
                       spend_limit_usd=cap / 2, concurrency=args.concurrency)
        plan = await runs.plan(ctx, conn, spec, RANKED)
        worst = plan["estimate"]["worst_case_usd"]
        print(f"{role:7} {model_id} via {endpoint}: {plan['estimate']['calls']} calls, typical "
              f"${plan['estimate']['typical_usd']:.4f}, worst ${worst:.4f}, share of cap ${cap / 2:.2f}; "
              f"ranked={plan['ranked']} {plan['not_ranked_reasons']} blocking={plan['blocking']}")
        if plan["blocking"]:
            print("blocked:", plan["blocking"])
            return 2
        if worst is not None and worst > cap / 2:
            print(f"refusing: worst case ${worst:.4f} exceeds this run's share of the cap")
            return 2
        plans.append((role, spec, plan))
    if not args.yes:
        print("Plan only. Re-run with --yes to send requests.")
        return 0
    run_ids = [(role, await runs.create(ctx, conn, spec, RANKED), spec) for role, spec, _ in plans]
    t0 = time.monotonic()
    await Worker(ctx).run(idle_exit_s=2.0)
    results = []
    for role, run_id, spec in run_ids:
        s = runs.summary(conn, run_id)
        results.append({
            "role": role, "run_id": run_id, "model_id": spec.model_id, "endpoint": spec.provider,
            "state": s["state"], "ranked": s["ranked"], "leaderboard_eligible": s["leaderboard_eligible"],
            "ineligible_reasons": s["ineligible_reasons"], "scores": s["scores"], "cost": s["cost"],
            "usage": s["usage"], "latency_ms": s["latency_ms"], "consistency": s["consistency"],
            "request": s["request"], "h1_contrast": h1_contrast(instance_scores(conn, run_id)),
            "h2_shadow_validity": shadow_association(conn, run_id),
        })
    baselines = json.loads((ROOT / "packs" / RANKED / "reports" / "baselines.json").read_text(encoding="utf-8"))
    total = sum(r["cost"]["spent_usd"] for r in results)
    report = {
        "kind": "mock dry run (NOT a pilot)" if mock else "live pilot",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "pack": RANKED, "cap_usd": cap,
        "spent_usd": total, "within_cap": total <= cap + 1e-9, "wall_s": round(time.monotonic() - t0, 1),
        "completed_models": sum(r["state"] == "completed" for r in results), "results": results,
        "baselines": baselines["pack"],
        "summary": "; ".join(f"{r['model_id']}: {r['state']}, overall {r['scores']['overall']}" for r in results)
                   + f"; spent ${total:.4f} of ${cap:.2f}",
    }
    write_report(report, mock)
    print(report["summary"])
    return 0


def fmt(v: float | None, d: int = 1) -> str:
    return "—" if v is None else f"{v:.{d}f}"


def write_report(rep: dict[str, Any], mock: bool) -> None:
    lines = [f"# {'Pilot tooling dry run (mock provider — not model results)' if mock else 'Pilot report'}", "",
             f"Generated {rep['generated_at']} · pack `{rep['pack']}` · Standard track · profile `standard` · "
             f"cap ${rep['cap_usd']:.2f}, spent ${rep['spent_usd']:.4f} ({'within' if rep['within_cap'] else 'OVER'} cap).",
             ""]
    if mock:
        lines += ["These numbers come from deterministic mock models and only demonstrate that the pilot tooling, "
                  "runner, analysis and report generation work end to end. They say nothing about any LLM.", ""]
    lines += ["## Prespecified results", "",
              "| Model | Endpoint | State | Overall (95% CI) | T1 | T2 | T3 | Valid | If valid | Optimal | H1: T1 − mean(T2,T3) (95% CI) |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rep["results"]:
        s = r["scores"]
        ci = s["interval_95"] or [None, None]
        h1 = r["h1_contrast"]
        h1s = "—" if h1.get("estimate") is None else f"{h1['estimate']:.1f} [{h1['interval_95'][0]:.1f}, {h1['interval_95'][1]:.1f}]"
        lines.append(f"| {r['model_id']} | {r['endpoint']} | {r['state']} | {fmt(s['overall'])} [{fmt(ci[0])}, {fmt(ci[1])}] | "
                     f"{fmt(s['tiers'].get('T1'))} | {fmt(s['tiers'].get('T2'))} | {fmt(s['tiers'].get('T3'))} | "
                     f"{fmt((s['valid_rate'] or 0) * 100, 0)}% | {fmt(s['conditional_quality'])} | "
                     f"{fmt((s['optimal_rate'] or 0) * 100, 0)}% | {h1s} |")
    b = rep["baselines"]
    lines += ["", f"Baselines on the same pack and aggregation: no-op {b['noop']:.1f}, uniform random legal edit "
              f"{b['random_legal_expected']:.1f}, uniform random candidate {b['random_candidate_expected']:.1f}, "
              f"local search {b['local_search']:.1f}, optimum {b['optimum']:.1f}.", "",
              "### Answer categories (H2)", ""]
    for r in rep["results"]:
        cats = ", ".join(f"{k} {v}" for k, v in sorted(r["scores"]["categories"].items(), key=lambda kv: -kv[1]))
        assoc = r["h2_shadow_validity"]
        lines.append(f"* **{r['model_id']}**: {cats}. Correlation of validity with shadow rejection rate: "
                     f"{fmt(assoc.get('correlation'), 2)} (n = {assoc['n']}).")
    lines += ["", "## Run facts", "", "| Model | Requested settings | Observed provider / model | Tokens in / out / reasoning | Cost | Mean latency |",
              "|---|---|---|---|---|---|"]
    for r in rep["results"]:
        c = r["consistency"]
        lines.append(f"| {r['model_id']} | `{json.dumps(r['request']['params'])}` | {', '.join(c['observed_providers']) or '—'} / "
                     f"{', '.join(c['observed_models']) or '—'} | {r['usage']['prompt_tokens']} / {r['usage']['completion_tokens']} / "
                     f"{r['usage']['reasoning_tokens']} | ${r['cost']['spent_usd']:.4f} | {fmt(r['latency_ms']['mean'], 0)} ms |")
    lines += ["", "## Exploratory notes", "",
              "None recorded automatically. Anything added below this line is exploratory, not prespecified.", "",
              "## Limitations", "",
              "* Two models, one repetition, 30 instances: a pilot, not a ranking. Intervals describe this pack's "
              "sampling design only.", "* The pack is public; contamination resistance is not claimed.",
              "* Provider-side settings not observable through the API are not reported as facts."]
    target = ROOT / "docs" / ("reports/PILOT_DRY_RUN.md" if mock else "research/PILOT_REPORT.md")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_target = ROOT / "docs" / ("reports/pilot_dry_run.json" if mock else "research/pilot_results.json")
    json_target.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    print(f"wrote {target}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cap", type=float, help="total USD cap for both runs (required for a live pilot)")
    ap.add_argument("--small")
    ap.add_argument("--large")
    ap.add_argument("--small-endpoint")
    ap.add_argument("--large-endpoint")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--yes", action="store_true", help="actually send requests")
    ap.add_argument("--dry-run-mock", action="store_true", help="use mock models (no network, no cost)")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
