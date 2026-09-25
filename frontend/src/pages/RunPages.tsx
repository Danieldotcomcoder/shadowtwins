import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { TERMINAL_STATES, useItems, useMeta, useRun, useRunEvents, useRuns } from "../api/hooks";
import { ActivityFeed, Controls, CostCard, ItemsTable, ScoreCard } from "../components/runs/RunParts";
import { Empty, ErrorBox, JobProgress, Loading, MockBadge, StateBadge } from "../components/ui/ui";
import { fmtAgo, fmtScore, fmtUsd, shortHash } from "../lib/format";
import { useDocumentTitle } from "../lib/hooks";
import { MODE_LABEL } from "../lib/labels";

export function RunsPage() {
  useDocumentTitle("Runs");
  const runs = useRuns();
  return (
    <div className="stack fade-in">
      <div className="page-head">
        <div>
          <h1>Runs</h1>
          <p>Every evaluation, ranked or not. Runs keep going on the server while no one is watching.</p>
        </div>
        <Link to="/" className="btn primary">New evaluation</Link>
      </div>
      {runs.isLoading && <Loading />}
      {runs.error && <ErrorBox error={runs.error} />}
      {runs.data && runs.data.length === 0 && (
        <div className="card"><Empty title="No runs yet" action={<Link to="/" className="btn primary">Evaluate a model</Link>}>
          Start a Quick Check to see how a model handles nine practice puzzles.</Empty></div>
      )}
      {runs.data && runs.data.length > 0 && (
        <div className="card table-wrap">
          <table className="data">
            <thead><tr><th>Model</th><th>Mode</th><th>State</th><th className="r">Score</th><th className="r hide-sm">Progress</th>
              <th className="r hide-sm">Cost</th><th className="hide-sm">Started</th></tr></thead>
            <tbody>
              {runs.data.map((r) => (
                <tr key={r.run_id}>
                  <td>
                    <Link to={`/runs/${encodeURIComponent(r.run_id)}`}>{r.model_id}</Link>
                    {r.is_mock && <> <MockBadge label="mock" /></>}
                    <div className="xsmall faint mono">{r.run_id}</div>
                  </td>
                  <td className="small">{MODE_LABEL[r.mode] ?? r.mode}<div className="xsmall faint">{r.profile_id}{r.ranked ? " · ranked" : ""}</div></td>
                  <td><StateBadge state={r.state} /></td>
                  <td className="r num">
                    {r.scores.official ? fmtScore(r.scores.overall)
                      : <span className="faint" title="provisional">{fmtScore(r.scores.provisional_overall)}*</span>}
                  </td>
                  <td className="r num small hide-sm">{r.scores.completed}/{r.scores.scheduled}</td>
                  <td className="r num small hide-sm">{fmtUsd(r.cost.spent_usd)}</td>
                  <td className="small dim hide-sm">{fmtAgo(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="xsmall faint" style={{ padding: "8px 12px" }}>* provisional: not every item has a completed answer.</p>
        </div>
      )}
    </div>
  );
}

export function RunPage() {
  const { runId = "" } = useParams();
  const run = useRun(runId);
  const items = useItems(runId);
  const meta = useMeta();
  const live = !!run.data && !TERMINAL_STATES.has(run.data.state);
  const [startAfter, setStartAfter] = useState<number | undefined>(undefined);
  useEffect(() => {
    if (run.data && startAfter === undefined) setStartAfter(run.data.last_event_id - 40);
  }, [run.data, startAfter]);
  const { events, status } = useRunEvents(runId, startAfter !== undefined, startAfter);
  useDocumentTitle(run.data ? `Run · ${run.data.model_id}` : "Run");
  if (run.isLoading) return <Loading label="Loading run" />;
  if (run.error || !run.data) return <ErrorBox error={run.error ?? "not found"} title="Run not found" />;
  const r = run.data;
  const operator = meta.data?.auth?.operator === true;
  return (
    <div className="stack fade-in">
      <div className="page-head">
        <div>
          <div className="row small dim" style={{ marginBottom: 6 }}><Link to="/runs">Runs</Link> / <span className="mono">{r.run_id}</span></div>
          <h1 className="row" style={{ gap: 12 }}>
            {r.model_id}
            <StateBadge state={r.state} />
            {r.is_mock && <MockBadge />}
          </h1>
          <p>
            {MODE_LABEL[r.mode] ?? r.mode} · profile <strong>{r.profile.label}</strong>
            {r.endpoint ? <> · pinned endpoint <span className="mono">{r.endpoint}</span></> : " · endpoint not pinned"}
            {" · "}pack <span className="mono">{r.pack_id}</span>
          </p>
          {r.state_reason && <p className="small">{r.state_reason}</p>}
        </div>
        <div className="row">
          <a className="btn small" href={api.exportUrl(r.run_id, "json")}>Export JSON</a>
          <a className="btn small" href={api.exportUrl(r.run_id, "csv")}>Export CSV</a>
          <Link className="btn small" to={`/models/${encodeURIComponent(r.model_id)}`}>Model history</Link>
        </div>
      </div>

      {r.is_mock && (
        <div className="banner info"><span className="icon">i</span>
          <div>This run used the <strong>mock provider</strong>, a deterministic test double. Its results are labelled and can never be ranked.</div></div>
      )}
      {!r.ranked && !r.is_mock && r.not_ranked_reasons.length > 0 && (
        <div className="banner info"><span className="icon">i</span><div>Unranked: {r.not_ranked_reasons.join("; ")}.</div></div>
      )}
      {r.state === "completed" && r.ranked && !r.leaderboard_eligible && (
        <div className="banner warn"><span className="icon">!</span><div>Not listed on the leaderboard: {r.ineligible_reasons.join("; ")}.</div></div>
      )}

      <section className="card card-pad stack-s" aria-label="Progress">
        <div className="spread">
          <h2>Progress</h2>
          <span className="small dim num">{r.scores.completed} of {r.scores.scheduled} items evaluated</span>
        </div>
        <JobProgress states={r.scores.states as Record<string, number>} total={r.scores.scheduled} />
        {(live || r.state === "paused" || r.state === "budget_stopped" || (r.scores.states as Record<string, number>).uncertain
          || (r.scores.states as Record<string, number>).failed) ? <Controls run={r} operator={operator} /> : null}
      </section>

      <div className="grid-2">
        <ScoreCard run={r} />
        <div className="stack">
          <CostCard run={r} />
          <section className="card card-pad stack-s" aria-label="Provenance">
            <h2>Provenance</h2>
            <dl className="kv">
              <dt>Fingerprint</dt><dd className="mono xsmall">{shortHash(r.fingerprint)}</dd>
              <dt>Pack hash</dt><dd className="mono xsmall">{shortHash(r.pack_hash)}</dd>
              <dt>Suite</dt><dd>{r.suite_version} (one benchmark: overall = Shadow Twins)</dd>
              <dt>Versions</dt><dd className="xsmall mono">{Object.entries(r.versions).map(([k, v]) => `${k} ${v}`).join(" · ")}</dd>
              <dt>Observed provider</dt>
              <dd>{r.consistency.observed_providers.join(", ") || "—"}
                {r.consistency.provider_matches_pin === true && <span className="badge ok" style={{ marginLeft: 6 }}>matches pin</span>}
                {r.consistency.provider_matches_pin === false && <span className="badge bad" style={{ marginLeft: 6 }}>differs from pin</span>}
              </dd>
              <dt>Observed model</dt><dd className="mono xsmall">{r.consistency.observed_models.join(", ") || "—"}</dd>
            </dl>
          </section>
        </div>
      </div>

      <div className="grid-2">
        <section className="card" aria-labelledby="items-title">
          <div className="card-head"><h2 id="items-title">Items</h2><span className="xsmall faint">Select a completed item to inspect it</span></div>
          {items.data ? <ItemsTable runId={r.run_id} items={items.data} showRep={r.repetitions > 1} /> : <Loading />}
        </section>
        <ActivityFeed events={events} status={status} />
      </div>
    </div>
  );
}
