/* Drift guard: the hand-written TS contract types must name exactly the properties of the committed
   JSON Schemas. The key maps below are checked by the compiler against the TS types
   (`satisfies Record<keyof T, true>`), and at runtime against the schema files. */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type {
  Check, Component, EditableCellInfo, EntranceInfo, GridState, OutcomeView, PairStatus, ParseOutcome,
  PathTrace, ShadowTwinsEvaluation, ShadowTwinsReplay, Silhouettes,
} from "./types";

const schema = (name: string) =>
  JSON.parse(readFileSync(join(__dirname, `../../../contracts/schemas/${name}.schema.json`), "utf-8"));

type Keys<T> = Record<keyof T, true>;
const replayKeys = {
  schema_version: true, replay_version: true, evaluator_version: true, instance_id: true, instance_hash: true,
  certificate_hash: true, budget: true, editable: true, entrances: true, original: true, optimal: true, model: true,
} satisfies Keys<ShadowTwinsReplay>;
const outcomeKeys = {
  label: true, edit: true, valid: true, category: true, checks: true, final: true, removed: true, added: true,
  silhouette_mismatch: true, pairs: true, raw_objective: true, v_star: true, score: true, opened: true, closed: true,
  move_count: true,
} satisfies Keys<OutcomeView>;
const gridKeys = {
  occupancy: true, silhouettes: true, empty_components: true, other_empty_cells: true, solid_components: true,
  entrance_component: true, paths: true,
} satisfies Keys<GridState>;
const evalKeys = {
  schema_version: true, instance_id: true, instance_hash: true, versions: true, parse: true, edit: true, valid: true,
  category: true, checks: true, final_occupancy: true, raw_objective: true, v_star: true, score: true, opened: true,
  closed: true, move_count: true, is_optimal: true,
} satisfies Keys<ShadowTwinsEvaluation>;
const defs: [string, Record<string, true>][] = [
  ["OutcomeView", outcomeKeys],
  ["GridState", gridKeys],
  ["Check", { code: true, status: true, message: true, cells: true, ids: true } satisfies Keys<Check>],
  ["Silhouettes", { x: true, y: true, z: true } satisfies Keys<Silhouettes>],
  ["Component", { id: true, cells: true, entrances: true } satisfies Keys<Component>],
  ["PathTrace", { i: true, j: true, cells: true } satisfies Keys<PathTrace>],
  ["PairStatus", { i: true, j: true, original: true, final: true, change: true } satisfies Keys<PairStatus>],
  ["EditableCellInfo", { id: true, cell: true, originally_solid: true } satisfies Keys<EditableCellInfo>],
  ["EntranceInfo", { index: true, label: true, cell: true } satisfies Keys<EntranceInfo>],
];

describe("TS contract types match the JSON Schemas", () => {
  const replay = schema("shadowtwins.replay.v1");
  it("ShadowTwinsReplay", () => expect(Object.keys(replay.properties).sort()).toEqual(Object.keys(replayKeys).sort()));
  for (const [name, keys] of defs) {
    it(name, () => expect(Object.keys(replay.$defs[name].properties).sort()).toEqual(Object.keys(keys).sort()));
  }
  it("ShadowTwinsEvaluation", () => {
    const ev = schema("shadowtwins.evaluation.v1");
    expect(Object.keys(ev.properties).sort()).toEqual(Object.keys(evalKeys).sort());
    const parseKeys = { parser_version: true, ok: true, category: true, detail: true, message: true, edit: true,
      json_text: true } satisfies Keys<ParseOutcome>;
    expect(Object.keys(ev.$defs.ParseOutcome.properties).sort()).toEqual(Object.keys(parseKeys).sort());
  });
});
