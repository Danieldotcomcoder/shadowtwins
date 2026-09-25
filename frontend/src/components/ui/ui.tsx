import * as Tooltip from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";
import { ApiError } from "../../api/client";
import { fmtScore } from "../../lib/format";
import { STATE_LABEL, STATE_TONE } from "../../lib/labels";

export function Tip({ content, children }: { content: ReactNode; children: ReactNode }) {
  return (
    <Tooltip.Root delayDuration={250}>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content className="tooltip" sideOffset={6}>
          {content}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export function StateBadge({ state }: { state: string }) {
  const tone = STATE_TONE[state] ?? "";
  const icon = { ok: "✓", bad: "✕", warn: "!", info: "●", accent: "", "": "" }[tone];
  return (
    <span className={`badge ${tone}`}>
      {state === "active" ? <span className="live-dot" aria-hidden /> : icon && <span aria-hidden>{icon}</span>}
      {STATE_LABEL[state] ?? state}
    </span>
  );
}

export function MockBadge({ label = "Mock · test double" }: { label?: string }) {
  return <span className="badge mock" title="Produced by the mock provider; never ranked">{label}</span>;
}

export function Stat({ k, v, hint }: { k: ReactNode; v: ReactNode; hint?: ReactNode }) {
  return (
    <div className="stat">
      <span className="k">{k}</span>
      <span className="v">{v}</span>
      {hint && <span className="xsmall faint">{hint}</span>}
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="row dim small" role="status" aria-live="polite" style={{ padding: "24px 0" }}>
      <span className="spinner" aria-hidden /> {label}…
    </div>
  );
}

export function SkeletonBlock({ h = 120 }: { h?: number }) {
  return <div className="skeleton" style={{ height: h }} aria-hidden />;
}

export function ErrorBox({ error, title = "Something went wrong" }: { error: unknown; title?: string }) {
  const msg = error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error);
  const status = error instanceof ApiError ? error.status : null;
  return (
    <div className="banner bad" role="alert">
      <span className="icon">✕</span>
      <div>
        <strong>{title}</strong>
        <div className="small">{status ? `${status} · ` : ""}{msg}</div>
      </div>
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children && <p className="small" style={{ maxWidth: 560, margin: "0 auto" }}>{children}</p>}
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  );
}

/** Score with its 95% bootstrap interval drawn on a 0-100 track. */
export function IntervalBar({ value, interval }: { value: number | null; interval: number[] | null | undefined }) {
  if (value === null) return <span className="faint">—</span>;
  const lo = interval?.[0] ?? value;
  const hi = interval?.[1] ?? value;
  return (
    <div className="interval" role="img" aria-label={`score ${fmtScore(value)}, 95% interval ${fmtScore(lo)} to ${fmtScore(hi)}`}>
      <div className="meter">
        <span style={{ left: `${lo}%`, width: `${Math.max(0.8, hi - lo)}%`, background: "rgba(125,211,192,0.35)" }} />
        <span style={{ left: `calc(${value}% - 1.5px)`, width: 3, background: "var(--accent)" }} />
      </div>
      <span className="xsmall faint num">{fmtScore(lo)}–{fmtScore(hi)}</span>
    </div>
  );
}

const STATE_COLORS: Record<string, string> = {
  completed: "var(--ok)",
  leased: "var(--info)",
  retry_wait: "var(--warn)",
  uncertain: "#d9a0ff",
  failed: "var(--bad)",
  cancelled: "#59606e",
  queued: "#2a313b",
};

export function JobProgress({ states, total }: { states: Record<string, number>; total: number }) {
  const order = ["completed", "leased", "retry_wait", "uncertain", "failed", "cancelled", "queued"];
  const done = states.completed ?? 0;
  return (
    <div className="stack-s">
      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}
        aria-label={`${done} of ${total} items completed`}>
        {order.filter((s) => states[s]).map((s) => (
          <span key={s} style={{ width: `${(100 * states[s]) / total}%`, background: STATE_COLORS[s] }} title={`${states[s]} ${s}`} />
        ))}
      </div>
      <div className="legend xsmall">
        {order.filter((s) => states[s]).map((s) => (
          <span key={s}><i className="sw" style={{ background: STATE_COLORS[s] }} aria-hidden /> {states[s]} {STATE_LABEL[s] ?? s}</span>
        ))}
      </div>
    </div>
  );
}
