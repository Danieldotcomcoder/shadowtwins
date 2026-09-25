"""``shadowtwins`` command line: certification, evaluation, replay and contract export.

    shadowtwins certify INSTANCE.json [-o CERT.json] [--verify]
    shadowtwins evaluate INSTANCE.json CERT.json RESPONSE.txt [--finish-reason length]
    shadowtwins replay INSTANCE.json CERT.json [RESPONSE.txt] [-o REPLAY.json]
    shadowtwins prompt INSTANCE.json
    shadowtwins export-contracts [--check]
    shadowtwins export-fixtures
    shadowtwins bench [--repeat N]

No command calls an LLM.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from benchcore.contracts import CompletionMeta, FinishReason

from . import evaluate as ev
from . import replay as rp
from . import solver
from .contracts import ShadowTwinsCertificate, ShadowTwinsInstance

ROOT = Path(__file__).resolve().parents[2]


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(obj: Any, path: Path | None) -> None:
    text = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    if path is None:
        sys.stdout.write(text)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def cmd_certify(args: argparse.Namespace) -> int:
    from .module import ShadowTwinsModule, attach_verification

    inst = ShadowTwinsInstance.model_validate(_load(args.instance))
    cert = solver.certify(inst)
    if args.verify:
        cert = attach_verification(cert, ShadowTwinsModule().independently_verify(inst, cert))
    _dump(cert.model_dump(mode="json"), args.output)
    return 0 if cert.independent_verification.status in ("verified", "not_run") else 1


def cmd_evaluate(args: argparse.Namespace) -> int:
    inst = ShadowTwinsInstance.model_validate(_load(args.instance))
    cert = ShadowTwinsCertificate.model_validate(_load(args.certificate))
    raw = args.response.read_text(encoding="utf-8")
    meta = CompletionMeta(finish_reason=FinishReason(args.finish_reason))
    result = ev.evaluate_text(inst, cert.core.v_star, raw, meta)
    _dump(result.model_dump(mode="json"), args.output)
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    inst = ShadowTwinsInstance.model_validate(_load(args.instance))
    cert = ShadowTwinsCertificate.model_validate(_load(args.certificate))
    model_eval = None
    if args.response:
        model_eval = ev.evaluate_text(inst, cert.core.v_star, args.response.read_text(encoding="utf-8"))
    _dump(rp.build_replay(inst, cert, model_eval).model_dump(mode="json"), args.output)
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    from .prompt import render_prompt

    inst = ShadowTwinsInstance.model_validate(_load(args.instance))
    for m in render_prompt(inst).messages:
        print(f"--- {m.role} ---\n{m.content}")
    return 0


def cmd_export_contracts(args: argparse.Namespace) -> int:
    from .contract_export import export_contracts

    changed = export_contracts(ROOT / "contracts", check=args.check)
    if args.check and changed:
        print("contract drift: " + ", ".join(changed))
        return 1
    print("contracts up to date" if args.check else f"wrote {len(changed)} changed file(s)")
    return 0


def cmd_export_fixtures(args: argparse.Namespace) -> int:
    from .contract_export import export_fixtures

    written = export_fixtures(ROOT / "contracts" / "fixtures")
    print(f"wrote {written} fixture files")
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    from .fixtures import snake_ten_by_ten

    inst = snake_ten_by_ten()
    times = []
    cert = solver.certify(inst)
    for _ in range(max(1, args.repeat)):
        t0 = time.perf_counter()
        cert = solver.certify(inst)
        times.append(time.perf_counter() - t0)
    print(json.dumps({
        "instance": inst.instance_id,
        "enumerated": cert.core.enumerated_count,
        "legal": cert.core.legal_count,
        "runs": args.repeat,
        "min_s": round(min(times), 4),
        "median_s": round(sorted(times)[len(times) // 2], 4),
    }, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="shadowtwins", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("certify")
    p.add_argument("instance", type=Path)
    p.add_argument("-o", "--output", type=Path)
    p.add_argument("--verify", action="store_true", help="also run the independent verifier")
    p.set_defaults(fn=cmd_certify)

    p = sub.add_parser("evaluate")
    p.add_argument("instance", type=Path)
    p.add_argument("certificate", type=Path)
    p.add_argument("response", type=Path)
    p.add_argument("--finish-reason", default="stop", choices=[f.value for f in FinishReason])
    p.add_argument("-o", "--output", type=Path)
    p.set_defaults(fn=cmd_evaluate)

    p = sub.add_parser("replay")
    p.add_argument("instance", type=Path)
    p.add_argument("certificate", type=Path)
    p.add_argument("response", type=Path, nargs="?")
    p.add_argument("-o", "--output", type=Path)
    p.set_defaults(fn=cmd_replay)

    p = sub.add_parser("prompt")
    p.add_argument("instance", type=Path)
    p.set_defaults(fn=cmd_prompt)

    p = sub.add_parser("export-contracts")
    p.add_argument("--check", action="store_true", help="fail if committed schemas differ")
    p.set_defaults(fn=cmd_export_contracts)

    p = sub.add_parser("export-fixtures")
    p.set_defaults(fn=cmd_export_fixtures)

    p = sub.add_parser("bench")
    p.add_argument("--repeat", type=int, default=5)
    p.set_defaults(fn=cmd_bench)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
