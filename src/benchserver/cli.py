"""``benchserver`` command line.

    benchserver migrate                 apply migrations and load shipped packs (run first)
    benchserver api [--host H --port P] serve the API and frontend (expects a migrated database)
    benchserver worker                  run the durable worker process
    benchserver supervise               migrate, then run API + worker under a small supervisor
    benchserver dev                     migrate, then API with an embedded worker (development)
    benchserver backup PATH             consistent online backup (WAL-safe)
    benchserver restore PATH            restore a backup (stop API and worker first)
    benchserver reevaluate RUN_ID       re-score stored responses offline and compare
    benchserver export RUN_ID [--format json|csv] [-o FILE]
    benchserver export-openapi [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import ROOT, load_settings


def _uvicorn(app: object, host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info", proxy_headers=False,  # type: ignore[arg-type]
                timeout_graceful_shutdown=20)


def openapi_document() -> dict:
    from .api.app import create_app
    from .context import AppContext

    settings = load_settings(db_path=Path(":memory:"), enable_mock_provider=False)
    app = create_app(AppContext(settings, providers={}))
    return app.openapi()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="benchserver", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    for name in ("api", "dev"):
        p = sub.add_parser(name)
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=8000)
    sub.add_parser("worker")
    p = sub.add_parser("supervise")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p = sub.add_parser("backup")
    p.add_argument("path", type=Path)
    p = sub.add_parser("restore")
    p.add_argument("path", type=Path)
    p = sub.add_parser("reevaluate")
    p.add_argument("run_id")
    p = sub.add_parser("export")
    p.add_argument("run_id")
    p.add_argument("--format", choices=["json", "csv"], default="json")
    p.add_argument("-o", "--output", type=Path)
    p = sub.add_parser("export-openapi")
    p.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "migrate":
        from .app_state import configure_logging, prepare_database

        settings = load_settings()
        configure_logging(settings, "migrate")
        print(json.dumps(prepare_database(settings), indent=2))
        return 0
    if args.cmd == "api":
        from .api.app import create_app
        from .app_state import startup

        _uvicorn(create_app(startup(run_migrations=False, component="api")), args.host, args.port)
        return 0
    if args.cmd == "dev":
        from .api.app import create_app
        from .app_state import startup

        _uvicorn(create_app(startup(component="dev"), embedded_worker=True), args.host, args.port)
        return 0
    if args.cmd == "worker":
        from .app_state import startup
        from .worker import main as worker_main

        worker_main(startup(run_migrations=False, component="worker"))
        return 0
    if args.cmd == "supervise":
        from .supervisor import supervise

        return supervise(args.host, args.port)
    if args.cmd == "backup":
        from .db import backup

        print(json.dumps(backup(load_settings().db_path, args.path), indent=2))
        return 0
    if args.cmd == "restore":
        from .db import restore

        print(json.dumps(restore(args.path, load_settings().db_path), indent=2))
        return 0
    if args.cmd in ("reevaluate", "export"):
        from . import exports
        from .app_state import startup

        ctx = startup(run_migrations=False, component="cli", providers={})
        conn = ctx.connect()
        try:
            if args.cmd == "reevaluate":
                report = exports.reevaluate(ctx, conn, args.run_id)
                print(json.dumps({k: report[k] for k in ("run_id", "checked", "mismatches", "aggregate_matches")},
                                 indent=2))
                return 0 if not report["mismatches"] and report["aggregate_matches"] else 1
            text = (exports.export_csv(conn, args.run_id) if args.format == "csv"
                    else json.dumps(exports.export_json(ctx, conn, args.run_id), indent=2))
            if args.output:
                args.output.write_text(text, encoding="utf-8")
            else:
                sys.stdout.write(text)
            return 0
        finally:
            conn.close()
    if args.cmd == "export-openapi":
        target = ROOT / "contracts" / "openapi.json"
        text = json.dumps(openapi_document(), indent=2, sort_keys=True) + "\n"
        if args.check:
            same = target.exists() and target.read_text(encoding="utf-8") == text
            print("openapi up to date" if same else "openapi drift: run `benchserver export-openapi`")
            return 0 if same else 1
        target.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {target}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
