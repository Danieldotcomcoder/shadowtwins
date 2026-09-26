# Operations

Single operator, single container. The image runs `tini` → `benchserver supervise`, which applies
migrations and loads the shipped packs (hash-checked, never recertified), then starts the API and
the worker as child processes, restarts a crashed child (at most 5 times in 5 minutes) and stops
both gracefully on SIGTERM.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Server-side key. Never sent to the browser, logged, stored or exported. |
| `ST_OPERATOR_TOKEN` | — | Bearer token for run controls. Setting it selects `token` auth. |
| `ST_AUTH_MODE` | `token` if a token is set, else `local` | `token`, `local` (loopback clients only), `readonly`, or `open` (explicit; only behind a trusted boundary) |
| `ST_DATA_DIR` | `/data` | SQLite database, logs, backups |
| `ST_WORKER_CONCURRENCY` | `8` | Global in-flight request limit (each run also has its own limit) |
| `ST_ENABLE_MOCK_PROVIDER` | `0` | Adds `mock/*` test doubles (never ranked) |
| `ST_CATALOG_TTL_S` | `3600` | OpenRouter catalog cache lifetime |
| `ST_HTTP_TIMEOUT_S` | `600` | Per-request read timeout (reasoning models can be slow) |
| `ST_LEASE_TTL_S` | `90` | Job lease; heartbeats extend it every 5 s |

Inside Docker, browser requests do not come from the container's loopback interface, so `local`
auth leaves the UI read-only. Set `ST_OPERATOR_TOKEN`, publish the port on `127.0.0.1`, and put a
TLS reverse proxy in front for any remote access. Public viewers can be allowed with
`ST_AUTH_MODE=token`: reads are public and controls need the token.

## Health

* `GET /api/health`: liveness (process up).
* `GET /api/ready`: readiness. The schema is current, the ranked pack is loaded and a worker
  heartbeat is recent. The Docker `HEALTHCHECK` uses this.
* `GET /api/admin/workers`: worker heartbeats.

## Resources and logs

The compose file limits the container to 1 GB of memory and 2 CPUs. Application logs rotate at
5 MB × 3 per component under `/data/logs`. Docker's own logs are capped with
`--log-opt max-size=10m --log-opt max-file=3`. Stop with a grace period of at least 35 s
(`--stop-timeout 40`): the worker lets in-flight requests finish (up to 30 s). Requests still in
flight at a hard kill are recovered as *uncertain* on the next start, never silently re-sent.

## Backup and restore (WAL-safe)

```bash
docker exec shadowtwins benchserver backup /data/backups/$(date +%F).db   # online, consistent
docker stop shadowtwins
docker run --rm -v shadowtwins-data:/data shadowtwins:0.1.0 restore /data/backups/2026-09-26.db
docker start shadowtwins
```

`backup` uses SQLite's online backup API, so it includes pages still in the WAL, and it
integrity-checks the copy. `restore` verifies the backup, then copies it into the live database
through the same API; stop the container first. Both are exercised by
`tools/container_acceptance.py`.

## Runs, costs and failures

* Every job is persisted before any request. Pausing stops new dispatch and lets in-flight
  requests settle. Cancelling cancels unsent jobs and records how in-flight ones ended.
* Before dispatch, each call reserves its worst-case cost. Dispatch stops (`budget_stopped`) when
  the next reservation would exceed the run limit. Raise the limit and resume from the run page.
* Transport, 5xx and 429 errors are retried with a fixed policy (4 attempts, exponential backoff,
  honouring `Retry-After`). `401`/`402` pause the run. A completed answer, however poor, is never
  retried.
* *Uncertain* jobs (sent, outcome unknown) keep the run incomplete until you choose **Rerun
  uncertain**, which may cost a second call and is logged.

## Upgrades

Migrations are numbered SQL files applied automatically before the worker starts. Packs are
immutable: a shipped pack whose hash changed is refused at startup. Corrections ship as new pack
ids and create new comparisons, and old results are never recomputed. Take a backup before upgrading.

## Exports and offline checks

* `GET /api/runs/{id}/export?format=json|csv` (UI: Export JSON / CSV), or
  `benchserver export RUN_ID`.
* `benchserver reevaluate RUN_ID` re-scores stored responses with the current evaluator and compares
  them with the stored scores and aggregate.
* `shadowtwins-verify packs/<pack>` reproduces every certificate without any engine code.
