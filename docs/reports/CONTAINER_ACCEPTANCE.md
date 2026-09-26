# Container acceptance

Image `shadowtwins:0.1.0` (251MB), Docker server 28.2.2, run 2026-09-26 05:02 UTC. Mock provider only (no paid calls).

**10/10 gates passed.** Reproduce: `docker build -t shadowtwins:0.1.0 .` then `uv run python tools/container_acceptance.py --image shadowtwins:0.1.0`.

| Gate | Result | Detail | Seconds |
|---|---|---|---|
| container becomes ready (migrations, packs, API, worker) | ✅ pass | ready after 2s | 2.2 |
| non-root user, one exposed port | ✅ pass | uid 10001; exposed ['8000/tcp']; image 251MB | 0.2 |
| docker healthcheck | ✅ pass | docker HEALTHCHECK reports healthy | 6.1 |
| frontend served; run controls require the operator token | ✅ pass | SPA served on the same origin; unauthenticated run creation → 401 | 0.1 |
| mock run end to end (API, worker, SSE, exports, offline re-evaluation) | ✅ pass | run_20260926_050200_936d8e: 9/9 evaluated, score 100.0 official, SSE replay 9 job_completed, CSV + re-evaluation match | 2.6 |
| secrets never leave the server | ✅ pass | key and token absent from container logs, log files and 5 API responses | 0.6 |
| restart keeps data | ✅ pass | run and scores intact after docker restart (named volume /data) | 3.6 |
| hard crash recovery | ✅ pass | SIGKILL mid-run → 2 in-flight job(s) marked uncertain (never silently re-sent), run incomplete with no official total; explicit rerun → completed, score 100.0 | 37.1 |
| graceful shutdown | ✅ pass | docker stop → exit code 0, in-flight requests settled; resumed after start and completed | 6.2 |
| WAL-safe backup and restore | ✅ pass | online backup (integrity ok); restore returned the database to 3 runs | 7.2 |
