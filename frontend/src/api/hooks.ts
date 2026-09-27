import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "./client";
import type { RunCreate, RunEvent } from "./types";

export const TERMINAL_STATES = new Set(["completed", "incomplete", "cancelled"]);

export function useMeta() {
  return useQuery({ queryKey: ["meta"], queryFn: api.meta, staleTime: 30_000 });
}

export function useCatalog() {
  return useQuery({ queryKey: ["catalog"], queryFn: api.catalog, staleTime: 5 * 60_000 });
}

export function useEndpoints(modelId: string | null) {
  return useQuery({
    queryKey: ["endpoints", modelId],
    queryFn: () => api.endpoints(modelId as string),
    enabled: !!modelId,
    staleTime: 5 * 60_000,
  });
}

export function useEstimate(spec: RunCreate | null) {
  return useQuery({
    queryKey: ["estimate", spec],
    queryFn: () => api.estimate(spec as RunCreate),
    enabled: !!spec,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useRuns(modelId?: string) {
  return useQuery({ queryKey: ["runs", modelId ?? null], queryFn: () => api.runs(modelId), refetchInterval: 15_000 });
}

export function useRun(runId: string) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.run(runId),
    refetchInterval: (q) => (q.state.data && TERMINAL_STATES.has(q.state.data.state) ? false : 10_000),
  });
}

export function useItems(runId: string) {
  return useQuery({ queryKey: ["items", runId], queryFn: () => api.items(runId) });
}

export function useJob(runId: string, jobId: number) {
  return useQuery({ queryKey: ["job", runId, jobId], queryFn: () => api.item(runId, jobId) });
}

export function useReplay(instanceId: string | undefined, runId?: string, jobId?: number) {
  return useQuery({
    queryKey: ["replay", instanceId, runId ?? null, jobId ?? null],
    queryFn: () => api.replay(instanceId as string, runId, jobId),
    enabled: !!instanceId,
    staleTime: Infinity,
  });
}

export function useLeaderboard(track: string, profileId?: string) {
  return useQuery({ queryKey: ["leaderboard", track, profileId ?? null], queryFn: () => api.leaderboard(track, profileId) });
}

export function useModelDetail(modelId: string) {
  return useQuery({ queryKey: ["model", modelId], queryFn: () => api.modelDetail(modelId) });
}

export function usePractice() {
  return useQuery({ queryKey: ["practice"], queryFn: api.practice, staleTime: Infinity });
}

export function useInstance(instanceId: string | undefined, reveal = false) {
  return useQuery({
    queryKey: ["instance", instanceId, reveal],
    queryFn: () => api.instance(instanceId as string, reveal),
    enabled: !!instanceId,
    staleTime: Infinity,
  });
}

export function useRunAction(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ action, value }: { action: string; value?: number }) => api.action(runId, action, value),
    onSuccess: (data) => {
      qc.setQueryData(["run", runId], data);
      qc.invalidateQueries({ queryKey: ["items", runId] });
    },
  });
}

const EVENT_TYPES = [
  "snapshot", "run_created", "run_state", "job_started", "job_completed", "job_retry_scheduled",
  "job_failed", "job_uncertain", "job_recovered", "jobs_requeued", "spend_limit", "run_cooldown", "end",
];

/** Live run updates over SSE. The server persists every event, so the stream resumes after
 *  reconnects (EventSource sends Last-Event-ID) and a closed browser never affects the run. */
export function useRunEvents(runId: string, enabled: boolean, startAfter?: number) {
  const qc = useQueryClient();
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [status, setStatus] = useState<"connecting" | "live" | "ended" | "reconnecting" | "off">("off");
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") {
      setStatus("off");
      return;
    }
    setStatus("connecting");
    // Replay recent persisted history first; afterwards EventSource resumes via Last-Event-ID.
    const after = startAfter === undefined ? "" : `?after=${Math.max(0, startAfter)}`;
    const es = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events${after}`);
    const refresh = () => {
      if (timer.current !== null) return;
      timer.current = window.setTimeout(() => {
        timer.current = null;
        qc.invalidateQueries({ queryKey: ["run", runId] });
        qc.invalidateQueries({ queryKey: ["items", runId] });
      }, 250);
    };
    const onEvent = (ev: MessageEvent) => {
      setStatus("live");
      if (ev.type === "end") {
        setStatus("ended");
        es.close();
        refresh();
        return;
      }
      if (ev.type === "snapshot") return;
      try {
        const parsed = JSON.parse(ev.data) as RunEvent;
        setEvents((prev) => [parsed, ...prev].slice(0, 60));
      } catch {
        /* ignore malformed event payloads */
      }
      refresh();
    };
    for (const t of EVENT_TYPES) es.addEventListener(t, onEvent as EventListener);
    es.onerror = () => setStatus((s) => (s === "ended" ? s : "reconnecting"));
    return () => {
      es.close();
      if (timer.current !== null) window.clearTimeout(timer.current);
      timer.current = null;
    };
  }, [runId, enabled, qc, startAfter]);

  return { events, status };
}
