/* Types for the benchmark-specific contracts (contracts/schemas/shadowtwins.*.v1.schema.json).
   Hand-written for readability; `contracts.test.ts` fails if the JSON Schemas' property names drift.
   API envelope types come from the generated `openapi.d.ts`. */

import type { components } from "./openapi";

export type Schemas = components["schemas"];
export type Meta = Schemas["Meta"];
export type Catalog = Schemas["Catalog"];
export type CatalogModel = Schemas["CatalogModel"];
export type Endpoint = Schemas["Endpoint"];
export type Profile = Schemas["Profile"];
export type RunCreate = Schemas["RunCreate"];
export type RunPlan = Schemas["RunPlan"];
export type RunSummary = Schemas["RunSummary"];
export type RunItem = Schemas["RunItem"];
export type Leaderboard = Schemas["Leaderboard"];
export type LeaderboardRow = Schemas["LeaderboardRow"];
export type ModelDetail = Schemas["ModelDetail"];
export type InstanceSummary = Schemas["InstanceSummary"];
export type PackSummary = Schemas["PackSummary"];
export type ScoreSummary = Schemas["ScoreSummary"];

export type Cell = [number, number, number];
export type Rows = number[][];

export type InvalidCategory =
  | "malformed_json"
  | "invalid_ids_or_types"
  | "duplicate_ids"
  | "wrong_source_occupancy"
  | "unequal_edit_counts"
  | "budget_exceeded"
  | "immutable_cell_modified"
  | "silhouette_changed"
  | "solid_disconnected"
  | "refusal"
  | "truncated";

export type CheckCode =
  | "parse"
  | "id_types"
  | "no_duplicates"
  | "source_occupancy"
  | "equal_counts"
  | "budget"
  | "immutable_cells"
  | "silhouette_x"
  | "silhouette_y"
  | "silhouette_z"
  | "solid_connected";

export interface Edit {
  remove: number[];
  add: number[];
}

export interface Check {
  code: CheckCode;
  status: "pass" | "fail" | "skipped";
  message: string;
  cells: Cell[];
  ids: number[];
}

export interface Silhouettes {
  x: Rows; // rows[z][y]
  y: Rows; // rows[z][x]
  z: Rows; // rows[y][x]
}

export interface Component {
  id: number;
  cells: Cell[];
  entrances: number[];
}

export interface PathTrace {
  i: number;
  j: number;
  cells: Cell[];
}

export interface GridState {
  occupancy: string;
  silhouettes: Silhouettes;
  empty_components: Component[];
  other_empty_cells: Cell[];
  solid_components: Component[];
  entrance_component: number[];
  paths: PathTrace[];
}

export type PairChange = "opened" | "closed" | "unchanged";

export interface PairStatus {
  i: number;
  j: number;
  original: boolean;
  final: boolean;
  change: PairChange;
}

export interface EditableCellInfo {
  id: number;
  cell: Cell;
  originally_solid: boolean;
}

export interface EntranceInfo {
  index: number;
  label: string;
  cell: Cell;
}

export interface OutcomeView {
  label: "model" | "optimal" | "noop" | "practice" | "custom";
  edit: Edit | null;
  valid: boolean;
  category: InvalidCategory | null;
  checks: Check[];
  final: GridState | null;
  removed: Cell[];
  added: Cell[];
  silhouette_mismatch: Silhouettes | null;
  pairs: PairStatus[];
  raw_objective: number | null;
  v_star: number;
  score: number;
  opened: number | null;
  closed: number | null;
  move_count: number | null;
}

export interface ShadowTwinsReplay {
  schema_version: "shadowtwins.replay.v1";
  replay_version: string;
  evaluator_version: string;
  instance_id: string;
  instance_hash: string;
  certificate_hash: string;
  budget: number;
  editable: EditableCellInfo[];
  entrances: EntranceInfo[];
  original: GridState;
  optimal: OutcomeView;
  model: OutcomeView | null;
}

export interface ParseOutcome {
  parser_version: string;
  ok: boolean;
  category: InvalidCategory | null;
  detail: string | null;
  message: string | null;
  edit: Edit | null;
  json_text: string | null;
}

export interface ShadowTwinsEvaluation {
  schema_version: "shadowtwins.evaluation.v1";
  instance_id: string;
  instance_hash: string;
  versions: Record<string, string>;
  parse: ParseOutcome;
  edit: Edit | null;
  valid: boolean;
  category: InvalidCategory | null;
  checks: Check[];
  final_occupancy: string | null;
  raw_objective: number | null;
  v_star: number;
  score: number;
  opened: number | null;
  closed: number | null;
  move_count: number | null;
  is_optimal: boolean;
}

export interface EvaluationEnvelope {
  benchmark_id: string;
  instance_id: string;
  instance_hash: string;
  valid: boolean;
  category: string | null;
  score: number;
  raw_objective: number | null;
  max_objective: number;
  versions: Record<string, string>;
  detail: ShadowTwinsEvaluation;
}

export interface InstanceCore {
  grid_size: 4;
  occupancy: string;
  entrances: Cell[];
  editable: Cell[];
  budget: number;
}

export interface ShadowTwinsInstance {
  schema_version: "shadowtwins.instance.v1";
  instance_id: string;
  core: InstanceCore;
  content_hash: string;
  meta: Record<string, unknown>;
}

export interface ChatMessage {
  role: "system" | "user";
  content: string;
}

export interface RenderedPrompt {
  benchmark_id: string;
  instance_id: string;
  protocol_version: string;
  messages: ChatMessage[];
  text_hash: string;
}

export interface InstanceDoc {
  instance: ShadowTwinsInstance;
  certificate: Record<string, unknown> & { core_hash: string; hidden?: string };
  certificate_verified: boolean;
  max_objective: number;
  pack_id: string;
  split: string;
  ranked: boolean;
  tier: string;
  prompt: RenderedPrompt;
  tokens_max: number | null;
}

export interface Attempt {
  attempt_id: number;
  number: number;
  state: string;
  created_at: string;
  sent_at: string | null;
  finished_at: string | null;
  request: Record<string, unknown> | null;
  response: Record<string, unknown> | null;
  http_status: number | null;
  error_category: string | null;
  error_message: string | null;
  generation_id: string | null;
  provider_name: string | null;
  response_model: string | null;
  finish_reason: string | null;
  native_finish_reason: string | null;
  content: string | null;
  refusal: string | null;
  reasoning_chars: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  reasoning_tokens: number | null;
  cost_usd: number | null;
  cost_source: string | null;
  latency_ms: number | null;
}

export interface JobDetail {
  job: Record<string, unknown> & { job_id: number; state: string; attempts: number; repetition: number };
  instance_id: string;
  tier: string;
  prompt: RenderedPrompt;
  certificate_hash: string;
  certificate_verified: boolean;
  max_objective: number;
  attempts: Attempt[];
  evaluation: EvaluationEnvelope | null;
}

export interface PracticeResult {
  unranked: true;
  evaluation: EvaluationEnvelope;
  replay: ShadowTwinsReplay;
}

export interface RunEvent {
  id: number;
  at: string;
  type: string;
  payload: Record<string, unknown>;
}
