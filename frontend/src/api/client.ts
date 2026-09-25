/* Thin typed client for the benchserver API. The browser never holds provider credentials; the
   optional operator token lives in sessionStorage (cleared when the tab closes) and is only sent
   as a Bearer header on this origin. */

import type {
  Catalog,
  Endpoint,
  InstanceDoc,
  InstanceSummary,
  JobDetail,
  Leaderboard,
  Meta,
  ModelDetail,
  PracticeResult,
  RunCreate,
  RunItem,
  RunPlan,
  RunSummary,
  ShadowTwinsReplay,
} from "./types";

const TOKEN_KEY = "st-operator-token";

export function getOperatorToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setOperatorToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: token only lives for this page */
  }
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

function messageOf(body: unknown, fallback: string): { message: string; detail: unknown } {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return { message: d, detail: d };
    if (d && typeof d === "object" && "message" in d) {
      return { message: String((d as { message: unknown }).message), detail: (d as { detail?: unknown }).detail };
    }
    if (Array.isArray(d)) return { message: d.map((e) => e?.msg ?? String(e)).join("; "), detail: d };
  }
  return { message: fallback, detail: body };
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getOperatorToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const text = await res.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }
  if (!res.ok) {
    const { message, detail } = messageOf(parsed, `${res.status} ${res.statusText}`);
    throw new ApiError(res.status, message, detail);
  }
  return parsed as T;
}

const q = (params: Record<string, string | number | boolean | null | undefined>) => {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  const s = sp.toString();
  return s ? `?${s}` : "";
};

export const api = {
  meta: () => request<Meta>("GET", "/api/meta"),
  catalog: () => request<Catalog>("GET", "/api/catalog"),
  refreshCatalog: () => request<Catalog>("POST", "/api/catalog/refresh"),
  endpoints: (modelId: string) =>
    request<{ model_id: string; endpoints: Endpoint[]; error: string | null }>(
      "GET",
      `/api/catalog/endpoints${q({ model_id: modelId })}`,
    ),
  setFavorite: (modelId: string, favorite: boolean) =>
    request<{ favorites: string[] }>("PUT", "/api/favorites", { model_id: modelId, favorite }),
  estimate: (spec: RunCreate) => request<RunPlan>("POST", "/api/runs/estimate", spec),
  createRun: (spec: RunCreate) => request<RunSummary>("POST", "/api/runs", spec),
  runs: (modelId?: string) => request<RunSummary[]>("GET", `/api/runs${q({ model_id: modelId })}`),
  run: (runId: string) => request<RunSummary>("GET", `/api/runs/${encodeURIComponent(runId)}`),
  items: (runId: string) => request<RunItem[]>("GET", `/api/runs/${encodeURIComponent(runId)}/items`),
  item: (runId: string, jobId: number) =>
    request<JobDetail>("GET", `/api/runs/${encodeURIComponent(runId)}/items/${jobId}`),
  action: (runId: string, action: string, value?: number) =>
    request<RunSummary>("POST", `/api/runs/${encodeURIComponent(runId)}/actions/${action}`,
      value === undefined ? undefined : { value }),
  instance: (instanceId: string, reveal = false) =>
    request<InstanceDoc>("GET", `/api/instances/${encodeURIComponent(instanceId)}${q({ reveal: reveal || undefined })}`),
  replay: (instanceId: string, runId?: string, jobId?: number) =>
    request<ShadowTwinsReplay>(
      "GET",
      `/api/instances/${encodeURIComponent(instanceId)}/replay${q({ run_id: runId, job_id: jobId })}`,
    ),
  leaderboard: (track: string, profileId?: string) =>
    request<Leaderboard>("GET", `/api/leaderboard${q({ track, profile_id: profileId })}`),
  modelDetail: (modelId: string) => request<ModelDetail>("GET", `/api/models/detail${q({ model_id: modelId })}`),
  practice: () => request<InstanceSummary[]>("GET", "/api/practice"),
  submitPractice: (instanceId: string, edit: { remove: number[]; add: number[] }) =>
    request<PracticeResult>("POST", `/api/practice/${encodeURIComponent(instanceId)}/submit`, edit),
  exportUrl: (runId: string, format: "json" | "csv") =>
    `/api/runs/${encodeURIComponent(runId)}/export?format=${format}`,
};
