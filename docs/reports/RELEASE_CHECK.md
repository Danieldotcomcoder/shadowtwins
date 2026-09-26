# Release acceptance matrix

Generated 2026-09-26 05:23 UTC by `tools/release_check.py --frontend` (container rows from `tools/container_acceptance.py`).

**21 pass · 0 fail · 1 blocked · 0 not run.**

| Gate | Result | Evidence |
|---|---|---|
| python lint (ruff) | ✅ pass | All checks passed! |
| python types (pyright) | ✅ pass | 0 errors, 0 warnings, 0 informations |
| python test suite | ✅ pass | 167 passed, 1 skipped in 48.03s |
| benchmark contracts unchanged | ✅ pass | contracts up to date |
| API contract unchanged | ✅ pass | openapi up to date |
| every ranked/practice/dev certificate independently reproduced | ✅ pass | 69/69 certificates reproduced; 0 file-hash problems; 15.86 s |
| token ceiling re-measured under the frozen panel | ✅ pass | 39 practice+ranked prompts re-rendered; panel st-tokpanel-1.0.0 max 699 ≤ 800; 0 differ from manifests |
| offline score recomputation and UI replay consistency (independent verifier) | ✅ pass | mock/random standard run: 30/30 evaluated, overall 6.5714; re-evaluation mismatches 0; CSV recomputation equal: True; 90 replay states checked against stverify, 0 problems |
| frontend unit tests (fixture cross-checks, contract drift) | ✅ pass | Tests  44 passed (44) |
| frontend production build | ✅ pass | ✓ built in 542ms |
| frontend end-to-end + accessibility (Playwright, axe) | ✅ pass | 10 passed (53.3s) |
| container: container becomes ready (migrations, packs, API, worker) | ✅ pass | ready after 2s |
| container: non-root user, one exposed port | ✅ pass | uid 10001; exposed ['8000/tcp']; image 251MB |
| container: docker healthcheck | ✅ pass | docker HEALTHCHECK reports healthy |
| container: frontend served; run controls require the operator token | ✅ pass | SPA served on the same origin; unauthenticated run creation → 401 |
| container: mock run end to end (API, worker, SSE, exports, offline re-evaluation) | ✅ pass | run_20260926_052013_acc514: 9/9 evaluated, score 100.0 official, SSE replay 9 job_completed, CSV + re-evaluation match |
| container: secrets never leave the server | ✅ pass | key and token absent from container logs, log files and 5 API responses |
| container: restart keeps data | ✅ pass | run and scores intact after docker restart (named volume /data) |
| container: hard crash recovery | ✅ pass | SIGKILL mid-run → 2 in-flight job(s) marked uncertain (never silently re-sent), run incomplete with no official total; explicit rerun → completed, score 100.0 |
| container: graceful shutdown | ✅ pass | docker stop → exit code 0, in-flight requests settled; resumed after start and completed |
| container: WAL-safe backup and restore | ✅ pass | online backup (integrity ok); restore returned the database to 3 runs |
| live pilot (small + larger model, explicit cap) | ⛔ blocked | OPENROUTER_API_KEY is not set in this environment |
