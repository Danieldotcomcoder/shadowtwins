# Shadow Twins — formal rules (st-rules-1.0.0)

Owner: P1. This document is the normative statement of the task semantics implemented in
`src/shadowtwins`. Changing anything here requires a version bump in
`src/shadowtwins/versions.py`, a dated entry in `docs/DECISIONS.md`, and coordinated consumer
updates. Scores are comparable only when every recorded version matches.

## 1. Coordinates

* The grid is 4 × 4 × 4. A cell is `(x, y, z)` with each coordinate in `0..3`.
* `x` is the **column**: it increases left to right within a printed row.
* `y` is the **row**: `y = 0` is printed first within a layer.
* `z` is the **layer**: `z = 0` is the bottom, `z = 3` the top.
* Flat index `i = x + 4y + 16z`. An occupancy is a 64-bit integer (or a 64-character `0/1`
  string whose character `i` is cell `i`); bit/character 1 means solid.
* Coordinates are anchored. Rotating or reflecting the object is never a free action. The 48 cube
  symmetries are used only as an analysis tool (invariance tests, duplicate detection).

Three.js renders with y up; the frontend maps task `(x, y, z)` to scene `(x, z, y)` and documents
this in one place (`frontend/src/three/coords.ts`).

## 2. Instance

An instance has:

* `A` — the original solid cells (`core.occupancy`). `A` is non-empty and forms **one
  face-connected component**.
* `T` — 2..8 distinct **entrances**: cells that are empty in `A` and lie on the boundary (some
  coordinate is 0 or 3). Entrances are immutable.
* `E` — the ordered **editable** list. Its position is the cell's **ID**. Entrances are never
  editable. Cells not in `E` never change.
* `b` — the relocation **budget**, 1..3.

The instance identity is `content_hash = sha256(canonical_json(core))`, where `core` contains
exactly `grid_size`, `occupancy`, `entrances`, `editable` and `budget`. `meta` (labels, tier,
seed, metrics) is excluded from the hash.

## 3. Edits

An answer is `{"remove": [...], "add": [...]}` with editable IDs. Removed IDs must be solid in
`A`, added IDs empty in `A`; both lists have equal length `r ≤ b`; no ID repeats or appears in
both lists. The final object `B` applies both lists **simultaneously**: `B = (A \ remove) ∪ add`.
No intermediate motion is simulated. The empty edit is always legal (because `A` is connected).

One move = one relocated cube, so `r` counts moves, not changed occupancy bits.

## 4. Legality of `B`

1. Only editable cells change and every entrance stays empty (guaranteed by the ID protocol;
   still checked).
2. **Exact silhouettes.** For each axis, the binary OR projection of `B` equals that of `A`:
   * `P_x(y, z) = OR_x [x,y,z solid]` — stored as `rows[z][y]`
   * `P_y(x, z) = OR_y [x,y,z solid]` — stored as `rows[z][x]`
   * `P_z(x, y) = OR_z [x,y,z solid]` — stored as `rows[y][x]`

   Rendering, perspective and lighting never decide validity.
3. **Solid connectivity.** `B`'s solid cells form one face-connected component.

## 5. Objective and score

Empty cells connect only through shared faces, inside the grid; no diagonals, gravity or travel
outside the grid. Unmarked boundary openings do not create external routes.

For entrances `i < j`, `C_X(i, j) = 1` when they lie in the same empty-cell component of `X`.

```
v(B) = sum over i<j of |C_B(i,j) - C_A(i,j)|
```

Opening and closing count equally; re-routing without changing reachability earns nothing;
pairs are counted, not paths.

`v*` is the exhaustively certified maximum of `v` over all legal edits. Since the no-op is legal
with `v = 0`, the minimum is 0 and

```
score = 100 * v(B) / v*          (valid answers)
score = 0                        (every invalid answer, with a category)
```

Instances with `v* = 0` are inadmissible and cannot be scored. There is no move-efficiency bonus.

## 6. Answer parsing (st-parser-1.0.0)

Accepted after stripping surrounding whitespace:

1. exactly one JSON object, or
2. exactly one code fence (```` ``` ```` or ```` ```json ````) containing exactly one JSON object.

The object must have exactly the keys `remove` and `add` (any order and whitespace), each an
array of at most 64 JSON integers. Rejected: prose before/after the answer, multiple objects or
fences, duplicate keys (ambiguous), NaN/Infinity, non-arrays, booleans (`true` is **not** 1),
fractional/exponent numbers (`2.0` is **not** 2), strings, nulls, responses longer than 20,000
characters. Answers are never repaired and no model is consulted.

Special categories:

* `truncated` — provider `finish_reason = length` and no complete answer parsed. A complete answer
  that happens to end at the limit is still used.
* `refusal` — provider refusal/content filter, or text with no `{` that matches the versioned
  refusal phrase list in `parser.py`. Text containing `{` is always treated as an attempted answer.

## 7. Evaluation order and categories (st-eval-1.0.0)

The first failing check determines the category; all computable checks are still reported so
invalid answers remain inspectable.

| # | Check | Category |
|---|---|---|
| 1 | parse | `malformed_json`, `invalid_ids_or_types`, `refusal`, `truncated` |
| 2 | id_types (range) | `invalid_ids_or_types` |
| 3 | no_duplicates | `duplicate_ids` |
| 4 | source_occupancy | `wrong_source_occupancy` |
| 5 | equal_counts | `unequal_edit_counts` |
| 6 | budget | `budget_exceeded` |
| 7 | immutable_cells | `immutable_cell_modified` (unreachable through IDs; defence in depth) |
| 8 | silhouette_x/y/z | `silhouette_changed` |
| 9 | solid_connected | `solid_disconnected` |

Infrastructure failures (transport errors, outages, unresolved rate limits) are **not** answers
and never receive a category here; they are handled by the runner (P3).

## 8. Certification (st-solver-1.0.0)

With `s` originally-solid and `e` originally-empty editable cells, every relocation set is
enumerated exactly once: `r = 0..min(b, s, e)`, each `r`-subset of solid IDs × each `r`-subset of
empty IDs, in ascending lexicographic order. The count is `Σ_r C(s,r)·C(e,r)` (16,526 for
`s = e = 10, b = 3`). There is no time limit and no heuristic; a certificate is only written after
the full enumeration.

Each certificate core records: instance id/hash; rules/solver/evaluator/protocol/generator
versions; `s`, `e`, `b`; expected and actual enumeration counts; legal count; `v*`, `v_min`;
optimal count; minimum moves for the optimum; histograms (overall and by move count); best
witness (lexicographically first optimum, i.e. fewest moves) and worst witness; rejection counts
charged to the first failing constraint (silhouette, then connectivity) and independent constraint
totals; a no-shadow ablation (same edit space without the silhouette rule; research only, never
scored); admissibility. `core_hash = sha256(canonical_json(core))`. Runtime and timestamps live
outside the hash.

**Independent verification.** `src/stverify` re-derives every core field with plain loops (sets
of tuples, explicit ray loops, BFS, bitmask-counted subsets) and imports nothing from the engine.
`shadowtwins-verify` reproduces certificates without any LLM call. A certificate counts as
certified for a ranked pack only when its `independent_verification.status` is `verified`.

## 9. Replay (st-replay-1.0.0)

Replays are derived deterministically from engine results: original/final occupancy, the three
masks, silhouette mismatch masks, removed/added cells, empty components containing entrances,
cavities, solid components, a pair-status matrix (`opened`/`closed`/`unchanged`), and one
breadth-first shortest path per connected pair (neighbour order `-x, +x, -y, +y, -z, +z`).
Pair changes are omitted for invalid answers so an invalid object is never animated as a valid
result. The optimal view always uses the certificate's best witness, re-evaluated at build time.

## 10. Worked fixtures (hand-checked)

All four are in `src/shadowtwins/fixtures.py`; the expected values below are asserted in
`tests/shadowtwins/test_solver.py` and reproduced by the independent verifier.

**Bent tunnel in a block** (`fx-bent-tunnel-block`). Full block minus tunnel
`(0,1,1)→(1,1,1)→(2,1,1)→(2,2,1)→(2,3,1)` and sealed entrance `C(3,0,3)`. Entrances
`A(0,1,1) B(2,3,1) C(3,0,3)`; editable `0:(1,1,1)` empty, `1:(1,1,2) 2:(3,0,2) 3:(3,1,3)` solid;
`b = 1`. Every silhouette ray is covered by the block, so all 4 candidates are legal. The three
relocations into `(1,1,1)` close A–B (v = 1); none can reach C with one move. Certificate:
enumerated 4, legal 4, histogram `{0:1, 1:3}`, `v* = 1`, best witness `remove [1] add [0]`.

**Shadow gate** (`fx-shadow-gate`). Same tunnel plus entrance `C(3,2,2)` behind the gate cube
`(3,2,1)` and an isolated cavity `(1,2,2)`. Editable `0:(3,2,1) 1:(3,1,1)` solid,
`2:(1,1,1) 3:(1,2,2)` empty, `b = 1`. The x-ray `(y=1, z=1)` holds three tunnel cells and the only
solid `(3,1,1)`.

| edit | effect | legal | v |
|---|---|---|---|
| no-op | — | yes | 0 |
| 0→2 | C joins tunnel; tunnel cut at (1,1,1): A–B closed, B–C opened | yes | 2 |
| 0→3 | C joins tunnel; cavity filled: A–C, B–C opened | yes | 2 |
| 1→2 | cube moves along its own x-ray: A–B closed | yes | 1 |
| 1→3 | x-ray (y=1,z=1) loses its only solid | **no** (silhouette) | — |

Certificate: enumerated 5, legal 4, histogram `{0:1, 1:1, 2:2}`, `v* = 2`, best `remove [0] add [2]`,
1 silhouette rejection. Edit 1→2 shows a relocation that is only legal because it stays on the
same ray.

**Shadow-protected straight tunnel** (`fx-straight-tunnel-zero`). Tunnel along x at `(y=1, z=1)`;
its x-ray is empty, so filling any tunnel cell changes `P_x` and closing A–B is impossible. Corner
cube `(3,3,3)` hangs on `(3,3,2)`. Result: `v* = 0` (inadmissible), 3 legal candidates,
2 silhouette rejections, 1 disconnection (also a silhouette failure). Without the shadow rule the
optimum would be 1 — the shadow constraint is what makes this instance trivial.

**Snake network** (`fx-snake-10x10`). Five entrances, `s = e = 10`, `b = 3`: enumerates exactly
16,526 candidates. Values are cross-checked against the verifier rather than by hand.

## 11. Reference runtime

Measured 2026-09-26 on the P1 development machine (Windows 11, Intel64 Family 6 Model 165,
Python 3.12.13), `uv run shadowtwins bench --repeat 7`:

| component | instance | candidates | time |
|---|---|---|---|
| optimized solver (with no-shadow ablation) | fx-snake-10x10 | 16,526 | 0.38 s median |
| independent verifier | fx-snake-10x10 | 16,526 | 5.8 s |

No release pack exists at P1; pack-level certification cost is measured by P2.
