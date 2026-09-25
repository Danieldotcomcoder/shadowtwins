import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useRunAction } from "../../api/hooks";
import type { RunEvent, RunItem, RunSummary } from "../../api/types";
import { fmtMs, fmtPct, fmtScore, fmtTokens, fmtUsd } from "../../lib/format";
import { categoryLabel, STATE_LABEL, TIER_NAME } from "../../lib/labels";
import { ErrorBox, IntervalBar, Stat, StateBadge } from "../ui/ui";

export function ScoreCard({ run }: { run: RunSummary }) {
  const s = run.scores;
  const official = s.official;
  const shown = official ? s.overall : s.provisional_overall;
  return (
    <section className="card card-pad stack" aria-labelledby="score-title">
      <div className="spread">
        <h2 id="score-title">Score</h2>
        {official ? <span className="badge ok">✓ official</span>
          : <span className="badge warn" title="Not every scheduled item has a completed answer">provisional · {s.completed}/{s.scheduled}</span>}
      </div>
      <div className="row" style={{ alignItems: "flex-end", gap: 18 }}>
        <div className="score-big" role="img" aria-label={`score ${fmtScore(shown)} out of 100`}>
          {fmtScore(shown)}<small>/100</small>
        </div>
        <div style={{ flex: 1, minWidth: 160 }}>
          <div className="xsmall faint" style={{ marginBottom: 6 }}>95% interval (instance bootstrap, stratified by tier)</div>
          <IntervalBar value={shown ?? null} interval={s.interval_95} />
        </div>
      </div>
      {!official && (
        <p className="xsmall faint">
          Provisional means over completed items only. An official total needs every scheduled item evaluated;
          failed, uncertain or cancelled items keep the run incomplete.
        </p>
      )}
      <div className="tier-bars">
        {Object.entries(s.tiers).map(([t, v]) => (
          <div key={t} className="tier-bar">
            <span className="small">{TIER_NAME[t] ?? t}</span>
            <div className="meter"><span style={{ left: 0, width: `${v}%`, background: "var(--accent)" }} /></div>
            <span className="num small">{fmtScore(v)}</span>
          </div>
        ))}
      </div>
      <div className="stats">
        <Stat k="Valid answers" v={fmtPct(s.valid_rate)} />
        <Stat k="Quality if valid" v={fmtScore(s.conditional_quality)} />
        <Stat k="Optimal answers" v={fmtPct(s.optimal_rate)} />
        <Stat k="Instances" v={s.instances} hint={run.repetitions > 1 ? `× ${run.repetitions} repetitions` : undefined} />
      </div>
      {Object.keys(s.categories).length > 0 && (
        <div className="cat-list">
          {Object.entries(s.categories).sort((a, b) => b[1] - a[1]).map(([c, n]) => (
            <span key={c} className={`badge ${c === "valid" ? "ok" : "bad"}`}>{c === "valid" ? "✓" : "✕"} {categoryLabel(c)} · {n}</span>
          ))}
        </div>
      )}
    </section>
  );
}

export function CostCard({ run }: { run: RunSummary }) {
  const c = run.cost;
  const pct = c.spend_limit_usd > 0 ? Math.min(100, (100 * (c.spent_usd + c.reserved_usd)) / c.spend_limit_usd) : 0;
  return (
    <section className="card card-pad stack-s" aria-labelledby="cost-title">
      <div className="spread"><h2 id="cost-title">Cost & usage</h2>
        {!c.pricing_known && <span className="badge warn">pricing unknown</span>}</div>
      <div className="meter" role="img" aria-label={`spent ${fmtUsd(c.spent_usd)} of ${fmtUsd(c.spend_limit_usd)}`}>
        <span style={{ left: 0, width: `${pct}%`, background: pct > 90 ? "var(--warn)" : "var(--info)" }} />
      </div>
      <div className="stats">
        <Stat k="Spent" v={fmtUsd(c.spent_usd)} hint={c.estimated_cost_attempts ? `${c.estimated_cost_attempts} estimated` : "provider-reported"} />
        <Stat k="Reserved" v={fmtUsd(c.reserved_usd)} hint="in-flight worst case" />
        <Stat k="Limit" v={fmtUsd(c.spend_limit_usd)} />
        <Stat k="Mean latency" v={fmtMs(run.latency_ms.mean)} />
        <Stat k="Tokens in / out" v={`${fmtTokens(run.usage.prompt_tokens)} / ${fmtTokens(run.usage.completion_tokens)}`}
          hint={run.usage.reasoning_tokens ? `${fmtTokens(run.usage.reasoning_tokens)} reasoning` : undefined} />
        <Stat k="Attempts" v={run.usage.attempts} />
      </div>
      {c.uncertain_cost_attempts > 0 && (
        <p className="xsmall faint">{c.uncertain_cost_attempts} uncertain attempt(s) are charged their full reservation.</p>
      )}
      <p className="xsmall faint">Cost and latency are reported separately and never affect the score.</p>
    </section>
  );
}

export function Controls({ run, operator }: { run: RunSummary; operator: boolean }) {
  const act = useRunAction(run.run_id);
  const [limitOpen, setLimitOpen] = useState(false);
  const [limit, setLimit] = useState(String(Math.max(run.cost.spend_limit_usd * 2, 1).toFixed(2)));
  const s = run.state;
  const states = run.scores.states as Record<string, number>;
  const busy = act.isPending;
  const btn = (label: string, action: string, cls = "", show = true, confirm?: string) =>
    show && (
      <button type="button" className={`btn small ${cls}`} disabled={!operator || busy}
        onClick={() => { if (!confirm || window.confirm(confirm)) act.mutate({ action }); }}>{label}</button>
    );
  return (
    <div className="stack-s">
      <div className="row">
        {btn("❚❚ Pause", "pause", "", s === "active" || s === "budget_stopped")}
        {btn("▶ Resume", "resume", "primary", s === "paused" || s === "budget_stopped")}
        {btn("Rerun uncertain", "rerun_uncertain", "", (states.uncertain ?? 0) > 0,
          "Uncertain requests may already have been processed and charged by the provider. Send them again?")}
        {btn("Retry failed", "retry_failed", "", (states.failed ?? 0) > 0)}
        {s !== "completed" && s !== "cancelled" && s !== "incomplete" && (
          <Dialog.Root open={limitOpen} onOpenChange={setLimitOpen}>
            <Dialog.Trigger asChild><button type="button" className="btn small" disabled={!operator}>Raise limit</button></Dialog.Trigger>
            <Dialog.Portal>
              <Dialog.Overlay className="overlay" />
              <Dialog.Content className="dialog">
                <Dialog.Title asChild><h2>Spending limit</h2></Dialog.Title>
                <Dialog.Description className="small dim" style={{ margin: "6px 0 14px" }}>
                  Currently {fmtUsd(run.cost.spend_limit_usd)}; spent {fmtUsd(run.cost.spent_usd)}, reserved {fmtUsd(run.cost.reserved_usd)}.
                </Dialog.Description>
                <form onSubmit={(e) => { e.preventDefault(); act.mutate({ action: "set_spend_limit", value: Number(limit) }); setLimitOpen(false); }}>
                  <div className="field"><label htmlFor="new-limit">New limit (USD)</label>
                    <input id="new-limit" className="input num" value={limit} onChange={(e) => setLimit(e.target.value)} /></div>
                  <div className="row" style={{ marginTop: 14, justifyContent: "flex-end" }}>
                    <Dialog.Close asChild><button type="button" className="btn">Cancel</button></Dialog.Close>
                    <button type="submit" className="btn primary">Save</button>
                  </div>
                </form>
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
        )}
        {btn("Cancel run", "cancel", "danger", !["completed", "cancelled", "incomplete", "cancelling"].includes(s),
          "Cancel this run? Unsent items are cancelled; in-flight requests finish and are recorded.")}
      </div>
      {!operator && <p className="xsmall faint">Controls need operator access.</p>}
      {act.error && <ErrorBox error={act.error} title="Action failed" />}
    </div>
  );
}

export function ItemsTable({ runId, items, showRep }: { runId: string; items: RunItem[]; showRep: boolean }) {
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label="Run items">
      <table className="data">
        <thead>
          <tr>
            <th>Instance</th><th>Tier</th>{showRep && <th className="r">Rep</th>}<th>State</th><th>Result</th>
            <th className="r">Score</th><th className="r">v / v*</th><th className="r hide-sm">Cost</th><th className="r hide-sm">Latency</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr key={it.job_id}>
              <td>
                {it.state === "completed" ? (
                  <Link to={`/runs/${encodeURIComponent(runId)}/items/${it.job_id}`} className="mono small">{it.instance_id}</Link>
                ) : <span className="mono small dim">{it.instance_id}</span>}
              </td>
              <td><span className="badge">{it.tier}</span></td>
              {showRep && <td className="r num">{it.repetition}</td>}
              <td><StateBadge state={it.state} />{it.attempts > 1 && <span className="xsmall faint"> · {it.attempts} attempts</span>}</td>
              <td className="small">
                {it.valid === null ? <span className="faint" title={it.last_error ?? undefined}>{it.last_error ? "no answer" : "—"}</span>
                  : it.valid ? <span className="ok-text">✓ valid</span>
                    : <span className="bad-text">✕ {categoryLabel(it.category)}</span>}
              </td>
              <td className="r num">{it.score === null ? "—" : fmtScore(it.score)}</td>
              <td className="r num small">{it.raw_objective ?? (it.valid === false ? "—" : "")}{it.max_objective !== null ? ` / ${it.max_objective}` : ""}</td>
              <td className="r num small hide-sm">{fmtUsd(it.cost_usd)}</td>
              <td className="r num small hide-sm">{fmtMs(it.latency_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const EVENT_TEXT: Record<string, (p: Record<string, unknown>) => string> = {
  job_completed: (p) => `${p.instance_id}: ${p.valid ? `valid, score ${fmtScore(p.score as number)}` : `invalid (${categoryLabel(p.category as string)})`}`,
  job_started: (p) => `${p.instance_id}: request sent (attempt ${p.attempt})`,
  job_retry_scheduled: (p) => `${p.instance_id}: ${p.category}, retry in ${p.delay_s}s`,
  job_failed: (p) => `${p.instance_id}: failed (${p.category}; ${p.reason})`,
  job_uncertain: (p) => `${p.instance_id ?? `job ${p.job_id}`}: outcome uncertain — ${p.note ?? p.category}`,
  job_recovered: (p) => `job ${p.job_id}: ${p.action}`,
  jobs_requeued: (p) => `${(p.job_ids as unknown[]).length} ${p.from} jobs requeued — ${p.note}`,
  run_state: (p) => `run ${STATE_LABEL[p.state as string] ?? p.state}${p.reason ? `: ${p.reason}` : ""}`,
  spend_limit: (p) => `spending limit set to ${fmtUsd(p.spend_limit_usd as number)}`,
  run_created: (p) => `run created with ${p.jobs} jobs`,
};

export function ActivityFeed({ events, status }: { events: RunEvent[]; status: string }) {
  return (
    <section className="card" aria-labelledby="feed-title">
      <div className="card-head">
        <h2 id="feed-title">Live activity</h2>
        <span className="xsmall faint row" aria-live="polite">
          {status === "live" && <span className="live-dot" aria-hidden />}{status === "off" ? "not live" : status}
        </span>
      </div>
      <ol className="feed" aria-live="off" tabIndex={0} aria-label="Recent run events">
        {events.length === 0 && <li className="faint small">Waiting for events…</li>}
        {events.map((e) => (
          <li key={e.id} className={`feed-item t-${e.type}`}>
            <span className="xsmall faint num">{new Date(e.at).toLocaleTimeString()}</span>
            <span className="small">{(EVENT_TEXT[e.type] ?? (() => e.type))(e.payload)}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
