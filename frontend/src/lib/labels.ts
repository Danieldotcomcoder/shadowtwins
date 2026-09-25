import type { CheckCode, InvalidCategory } from "../api/types";

export const CATEGORY_LABEL: Record<string, string> = {
  valid: "Valid",
  malformed_json: "Malformed or ambiguous JSON",
  invalid_ids_or_types: "Invalid IDs or types",
  duplicate_ids: "Duplicate IDs",
  wrong_source_occupancy: "Wrong source occupancy",
  unequal_edit_counts: "Unequal edit counts",
  budget_exceeded: "Budget exceeded",
  immutable_cell_modified: "Immutable cell modified",
  silhouette_changed: "Silhouette changed",
  solid_disconnected: "Solid disconnected",
  refusal: "Refusal",
  truncated: "Truncated",
};

export const categoryLabel = (c: InvalidCategory | string | null | undefined) =>
  c ? CATEGORY_LABEL[c] ?? c : "Valid";

export const CHECK_LABEL: Record<CheckCode, string> = {
  parse: "One JSON answer",
  id_types: "IDs in range",
  no_duplicates: "No repeated IDs",
  source_occupancy: "Removed solid, added empty",
  equal_counts: "Equal remove/add counts",
  budget: "Within move budget",
  immutable_cells: "Only editable cells change",
  silhouette_x: "Shadow along x unchanged",
  silhouette_y: "Shadow along y unchanged",
  silhouette_z: "Shadow along z unchanged",
  solid_connected: "Solid stays one piece",
};

export const STATE_LABEL: Record<string, string> = {
  active: "Running",
  paused: "Paused",
  budget_stopped: "Budget stop",
  cancelling: "Cancelling",
  cancelled: "Cancelled",
  completed: "Completed",
  incomplete: "Incomplete",
  queued: "Queued",
  leased: "In flight",
  retry_wait: "Retry scheduled",
  uncertain: "Uncertain",
  failed: "Failed",
};

export const STATE_TONE: Record<string, "ok" | "warn" | "bad" | "info" | "accent" | ""> = {
  active: "info",
  paused: "warn",
  budget_stopped: "warn",
  cancelling: "warn",
  cancelled: "",
  completed: "ok",
  incomplete: "bad",
  queued: "",
  leased: "info",
  retry_wait: "warn",
  uncertain: "warn",
  failed: "bad",
};

export const TIER_NAME: Record<string, string> = {
  T1: "T1 · single relocation",
  T2: "T2 · paired relocations",
  T3: "T3 · coordinated search",
};

export const MODE_LABEL: Record<string, string> = {
  quick_check: "Quick Check",
  standard: "Standard",
  repeated: "Repeated Evaluation",
};
