# Ownership boundaries

One accountable owner per area. Shared contracts, root lockfiles and integration changes have one
named owner; changes by anyone else need a decision entry in `docs/DECISIONS.md`.

| Path | Owner | Notes |
|---|---|---|
| `src/benchcore/` (interface, contracts, hashing, registry) | P1 | Run-level contracts extended by P3 via decision entries |
| `src/benchcore/aggregate.py` | P3 | Aggregation, intervals, leaderboard policy |
| `src/shadowtwins/{grid,engine,parser,evaluate,solver,replay,transforms,contracts,versions,fixtures,module,contract_export,cli}.py` | P1 | Benchmark semantics. Never silently change scoring, token limits or pack identity |
| `src/shadowtwins/prompt.py` | P2 | Prompt serialization (`st-protocol-*`) |
| `src/shadowtwins/{generator,metrics,baselines,packs,tokens}.py` | P2 | Generation, admission, baselines, packs, token panel |
| `src/stverify/` | P1 | Independent verifier; must never import `shadowtwins` or `benchcore` |
| `src/benchserver/` | P3 | API, DB migrations, worker, providers, exports |
| `contracts/` (schemas, VERSIONS.json, fixtures) | P1 | Regenerate with `shadowtwins export-contracts` / `export-fixtures` |
| `packs/` | P2 | Frozen after release; corrections create new pack versions |
| `docs/research/` | P2 (P5 appends pilot report) | |
| `frontend/` | P4 | |
| `Dockerfile`, `docker/`, release docs | P5 | |
| `pyproject.toml`, `uv.lock`, `frontend/pnpm-lock.yaml` | P1 → P5 at integration | Root lockfiles: one owner at a time |

Later prompts:

* **P2** builds on `shadowtwins.solver.certify`, `shadowtwins.transforms.instance_canonical_key`
  and `stverify` to generate, admit and freeze packs.
* **P3** consumes `benchcore.interface.BenchmarkModule` through `benchcore.registry` and stores the
  generic `EvaluationEnvelope`; it never imports Shadow Twins geometry directly.
* **P4** renders `shadowtwins.replay.v1` documents (see `contracts/fixtures/replays/`) and never
  decides scores.
* **P5** owns the integration branch (`main`) and release gates.
