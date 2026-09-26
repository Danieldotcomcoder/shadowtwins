"""Container release acceptance (P5). Requires Docker and a built image.

    docker build -t shadowtwins:0.1.0 .
    uv run python tools/container_acceptance.py --image shadowtwins:0.1.0

Runs the image with a throwaway volume and the mock provider (no paid calls), and records the
actual outcome of each gate in docs/reports/CONTAINER_ACCEPTANCE.md (+ .json).
"""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
NAME = "st-accept"
VOLUME = "st-accept-data"
PORT = 8791
TOKEN = "accept-" + secrets.token_urlsafe(18)
FAKE_KEY = "sk-or-v1-ACCEPTANCE-FAKE-" + secrets.token_hex(8)
BASE = f"http://127.0.0.1:{PORT}"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def sh(*args: str, check: bool = True, timeout: float = 180) -> subprocess.CompletedProcess[str]:
    r = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed: {r.stderr[-800:]}")
    return r


def docker(*args: str, check: bool = True, timeout: float = 180) -> subprocess.CompletedProcess[str]:
    return sh("docker", *args, check=check, timeout=timeout)


def wait_ready(timeout: float = 150) -> float:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            r = httpx.get(f"{BASE}/api/ready", timeout=3)
            if r.status_code == 200:
                return time.monotonic() - t0
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise TimeoutError("container did not become ready")


def run_state(run_id: str) -> dict[str, Any]:
    return httpx.get(f"{BASE}/api/runs/{run_id}", timeout=10).json()


def wait_state(run_id: str, states: set[str], timeout: float = 120) -> dict[str, Any]:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        s = run_state(run_id)
        if s["state"] in states:
            return s
        time.sleep(1)
    raise TimeoutError(f"run {run_id} did not reach {states}; last state {s['state']}")


def create(model: str, concurrency: int = 4, mode: str = "quick_check") -> str:
    r = httpx.post(f"{BASE}/api/runs", headers=AUTH, timeout=30, json={
        "model_id": model, "profile_id": "standard", "mode": mode, "spend_limit_usd": 5, "concurrency": concurrency})
    if r.status_code != 201:
        raise RuntimeError(f"create failed: {r.status_code} {r.text[:300]}")
    return r.json()["run_id"]


def start_container(image: str) -> None:
    docker("run", "-d", "--name", NAME, "-p", f"127.0.0.1:{PORT}:8000", "-v", f"{VOLUME}:/data",
           "-e", f"ST_OPERATOR_TOKEN={TOKEN}", "-e", "ST_ENABLE_MOCK_PROVIDER=1", "-e", f"OPENROUTER_API_KEY={FAKE_KEY}",
           "--stop-timeout", "40", "--log-opt", "max-size=10m", "--log-opt", "max-file=3", image)


def cleanup() -> None:
    docker("rm", "-f", NAME, check=False)
    docker("volume", "rm", "-f", VOLUME, check=False)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default="shadowtwins:0.1.0")
    args = ap.parse_args()
    results: list[dict[str, Any]] = []

    def gate(name: str, fn: Any) -> None:
        t0 = time.monotonic()
        try:
            rec = {"gate": name, "status": "pass", "detail": fn()}
        except Exception as exc:  # record, continue with the other gates
            rec = {"gate": name, "status": "fail", "detail": f"{type(exc).__name__}: {exc}"}
        rec["seconds"] = round(time.monotonic() - t0, 1)
        results.append(rec)
        print(f"{rec['status'].upper()} {name}: {rec['detail']}")

    cleanup()
    size_mb = docker("image", "ls", args.image, "--format", "{{.Size}}").stdout.strip()
    start_container(args.image)

    gate("container becomes ready (migrations, packs, API, worker)", lambda: f"ready after {wait_ready():.0f}s")

    def nonroot() -> str:
        uid = docker("exec", NAME, "id", "-u").stdout.strip()
        assert uid == "10001", uid
        ports = json.loads(docker("inspect", NAME).stdout)[0]["Config"]["ExposedPorts"]
        assert list(ports) == ["8000/tcp"], ports
        return f"uid {uid}; exposed {list(ports)}; image {size_mb}"
    gate("non-root user, one exposed port", nonroot)

    def healthy() -> str:
        t0 = time.monotonic()
        while time.monotonic() - t0 < 90:
            st = json.loads(docker("inspect", NAME).stdout)[0]["State"].get("Health", {}).get("Status")
            if st == "healthy":
                return "docker HEALTHCHECK reports healthy"
            time.sleep(3)
        raise AssertionError(f"health status {st}")
    gate("docker healthcheck", healthy)

    def frontend_and_auth() -> str:
        html = httpx.get(f"{BASE}/runs/anything", timeout=10).text
        assert '<div id="root">' in html
        meta = httpx.get(f"{BASE}/api/meta", timeout=10).json()
        assert meta["auth"]["mode"] == "token" and meta["auth"]["operator"] is False
        r = httpx.post(f"{BASE}/api/runs", timeout=10, json={"model_id": "mock/optimal", "profile_id": "standard",
                                                              "mode": "quick_check", "spend_limit_usd": 1})
        assert r.status_code == 401, r.status_code
        return "SPA served on the same origin; unauthenticated run creation → 401"
    gate("frontend served; run controls require the operator token", frontend_and_auth)

    state: dict[str, str] = {}

    def full_run() -> str:
        run_id = create("mock/optimal")
        state["run"] = run_id
        s = wait_state(run_id, {"completed"})
        assert s["scores"]["official"] and s["scores"]["overall"] == 100.0
        with httpx.stream("GET", f"{BASE}/api/runs/{run_id}/events?after=0", timeout=30) as resp:
            body = "".join(resp.iter_text())
        completed = body.count("event: job_completed")
        assert completed == 9 and "event: end" in body
        csv = httpx.get(f"{BASE}/api/runs/{run_id}/export?format=csv", timeout=30).text
        assert len(csv.strip().splitlines()) == 10
        re = httpx.get(f"{BASE}/api/runs/{run_id}/reevaluate", timeout=60).json()
        assert re["mismatches"] == [] and re["aggregate_matches"]
        return f"{run_id}: 9/9 evaluated, score 100.0 official, SSE replay 9 job_completed, CSV + re-evaluation match"
    gate("mock run end to end (API, worker, SSE, exports, offline re-evaluation)", full_run)

    def secrets_check() -> str:
        blobs = [docker("logs", NAME).stdout + docker("logs", NAME).stderr,
                 docker("exec", NAME, "sh", "-c", "cat /data/logs/*.log").stdout]
        for path in ("/api/meta", f"/api/runs/{state['run']}", f"/api/runs/{state['run']}/export?format=json",
                     "/api/catalog", "/api/openapi.json"):
            blobs.append(httpx.get(f"{BASE}{path}", headers=AUTH, timeout=60).text)
        leaks = [i for i, b in enumerate(blobs) if FAKE_KEY in b or TOKEN in b]
        assert not leaks, leaks
        return f"key and token absent from container logs, log files and {len(blobs) - 2} API responses"
    gate("secrets never leave the server", secrets_check)

    def restart_persistence() -> str:
        docker("restart", "-t", "40", NAME, timeout=120)
        wait_ready()
        s = run_state(state["run"])
        assert s["state"] == "completed" and s["scores"]["overall"] == 100.0
        return "run and scores intact after docker restart (named volume /data)"
    gate("restart keeps data", restart_persistence)

    def crash_recovery() -> str:
        run_id = create("mock/slow", concurrency=2)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 60:
            s = run_state(run_id)
            if s["scores"]["states"].get("completed", 0) >= 1 and s["scores"]["states"].get("leased", 0) >= 1:
                break
            time.sleep(0.2)
        docker("kill", "-s", "KILL", NAME)
        docker("start", NAME)
        wait_ready()
        s = wait_state(run_id, {"completed", "incomplete"}, timeout=180)
        uncertain = s["scores"]["states"].get("uncertain", 0)
        assert s["state"] == "incomplete" and uncertain >= 1, s["scores"]["states"]
        assert s["scores"]["overall"] is None
        r = httpx.post(f"{BASE}/api/runs/{run_id}/actions/rerun_uncertain", headers=AUTH, timeout=30)
        assert r.status_code == 200, r.text
        s = wait_state(run_id, {"completed"}, timeout=120)
        return (f"SIGKILL mid-run → {uncertain} in-flight job(s) marked uncertain (never silently re-sent), "
                f"run incomplete with no official total; explicit rerun → completed, score {s['scores']['overall']}")
    gate("hard crash recovery", crash_recovery)

    def graceful_stop() -> str:
        run_id = create("mock/slow", concurrency=2)
        time.sleep(1.5)
        docker("stop", "-t", "40", NAME, timeout=120)
        code = json.loads(docker("inspect", NAME).stdout)[0]["State"]["ExitCode"]
        logs = docker("logs", "--tail", "40", NAME)
        assert "supervisor stopped" in logs.stdout + logs.stderr
        docker("start", NAME)
        wait_ready()
        s = wait_state(run_id, {"completed", "incomplete"}, timeout=120)
        assert s["state"] == "completed" and not s["scores"]["states"].get("uncertain"), s["scores"]["states"]
        return f"docker stop → exit code {code}, in-flight requests settled; resumed after start and completed"
    gate("graceful shutdown", graceful_stop)

    def backup_restore() -> str:
        out = docker("exec", NAME, "benchserver", "backup", "/data/backups/accept.db").stdout
        assert '"integrity": "ok"' in out, out
        before = len(httpx.get(f"{BASE}/api/runs", timeout=30).json())
        extra = create("mock/optimal")
        wait_state(extra, {"completed"})
        assert len(httpx.get(f"{BASE}/api/runs", timeout=30).json()) == before + 1
        docker("stop", "-t", "40", NAME, timeout=120)
        docker("run", "--rm", "-v", f"{VOLUME}:/data", args.image, "restore", "/data/backups/accept.db", timeout=120)
        docker("start", NAME)
        wait_ready()
        after = len(httpx.get(f"{BASE}/api/runs", timeout=30).json())
        assert after == before, (before, after)
        return f"online backup (integrity ok); restore returned the database to {before} runs"
    gate("WAL-safe backup and restore", backup_restore)

    logs = docker("logs", NAME, check=False)
    cleanup()
    passed = sum(r["status"] == "pass" for r in results)
    report = {"image": args.image, "image_size": size_mb, "docker_server": docker("version", "--format",
              "{{.Server.Version}}").stdout.strip(), "passed": passed, "total": len(results), "results": results,
              "log_tail": (logs.stdout + logs.stderr)[-3000:]}
    out = ROOT / "docs" / "reports"
    (out / "CONTAINER_ACCEPTANCE.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# Container acceptance", "",
             f"Image `{args.image}` ({size_mb}), Docker server {report['docker_server']}, run "
             f"{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. Mock provider only (no paid calls).", "",
             f"**{passed}/{len(results)} gates passed.** Reproduce: `docker build -t {args.image} .` then "
             f"`uv run python tools/container_acceptance.py --image {args.image}`.", "",
             "| Gate | Result | Detail | Seconds |", "|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['gate']} | {'✅ pass' if r['status'] == 'pass' else '❌ fail'} | {r['detail']} | {r['seconds']} |")
    (out / "CONTAINER_ACCEPTANCE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{passed}/{len(results)} gates passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
