/* Verifies that everything the viewer draws matches the authoritative fixtures: silhouettes equal an
   independent TS re-computation from occupancy, mismatch masks equal the XOR of original and final,
   every route is a chain of face-adjacent empty cells between its entrances, and pair statuses agree
   with component labels. */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { GridState, OutcomeView, ShadowTwinsReplay } from "../api/types";
import { coords, index, linkedPairs, projections, toScene, validPath } from "./geometry";

const DIR = join(__dirname, "../../../contracts/fixtures/replays");
const files = readdirSync(DIR).filter((f) => f.endsWith(".json"));
const load = (f: string) => JSON.parse(readFileSync(join(DIR, f), "utf-8")) as ShadowTwinsReplay;

function checkState(r: ShadowTwinsReplay, state: GridState) {
  expect(state.silhouettes).toEqual(projections(state.occupancy));
  for (const p of state.paths) {
    expect(validPath(state, p.cells, r.entrances[p.i].cell, r.entrances[p.j].cell)).toBe(true);
  }
  const linked = linkedPairs(state);
  expect(new Set(state.paths.map((p) => `${p.i}-${p.j}`))).toEqual(linked);
}

function checkOutcome(r: ShadowTwinsReplay, o: OutcomeView) {
  if (!o.final) {
    expect(o.silhouette_mismatch).toBeNull();
    return;
  }
  checkState(r, o.final);
  for (const axis of ["x", "y", "z"] as const) {
    const a = r.original.silhouettes[axis];
    const b = o.final.silhouettes[axis];
    const xor = a.map((row, v) => row.map((val, u) => Number(val !== b[v][u])));
    expect(o.silhouette_mismatch?.[axis]).toEqual(xor);
  }
  if (!o.valid) {
    expect(o.pairs).toEqual([]);
    return;
  }
  const before = linkedPairs(r.original);
  const after = linkedPairs(o.final);
  let opened = 0;
  let closed = 0;
  for (const p of o.pairs) {
    const key = `${p.i}-${p.j}`;
    expect(p.original).toBe(before.has(key));
    expect(p.final).toBe(after.has(key));
    const change = p.final && !p.original ? "opened" : p.original && !p.final ? "closed" : "unchanged";
    expect(p.change).toBe(change);
    if (change === "opened") opened++;
    if (change === "closed") closed++;
  }
  expect(opened).toBe(o.opened);
  expect(closed).toBe(o.closed);
  expect(o.raw_objective).toBe(opened + closed);
  expect(o.score).toBeCloseTo((100 * (opened + closed)) / o.v_star, 10);
  // removed/added cells are exactly the occupancy differences
  const diff = (from: string, to: string) =>
    [...from].map((c, i) => (c === "1" && to[i] === "0" ? i : -1)).filter((i) => i >= 0).map((i) => coords(i).join(","));
  expect(o.removed.map((c) => c.join(",")).sort()).toEqual(diff(r.original.occupancy, o.final.occupancy).sort());
  expect(o.added.map((c) => c.join(",")).sort()).toEqual(diff(o.final.occupancy, r.original.occupancy).sort());
}

describe("coordinate convention", () => {
  it("round-trips indices and maps z to the scene's up axis", () => {
    for (let i = 0; i < 64; i++) expect(index(...coords(i))).toBe(i);
    expect(index(1, 0, 0)).toBe(1);
    expect(index(0, 1, 0)).toBe(4);
    expect(index(0, 0, 1)).toBe(16);
    expect(toScene([0, 0, 3])[1]).toBeGreaterThan(toScene([0, 0, 0])[1]);
  });
});

describe("replay fixtures match what the viewer draws", () => {
  it("has fixtures", () => expect(files.length).toBeGreaterThan(15));
  for (const f of files) {
    it(f, () => {
      const r = load(f);
      checkState(r, r.original);
      checkOutcome(r, r.optimal);
      expect(r.optimal.valid).toBe(true);
      expect(r.optimal.raw_objective).toBe(r.optimal.v_star);
      if (r.model) checkOutcome(r, r.model);
    });
  }
});
