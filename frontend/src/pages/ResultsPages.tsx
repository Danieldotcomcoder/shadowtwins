import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useLeaderboard, useMeta, useModelDetail } from "../api/hooks";
import { ScoreCard } from "../components/runs/RunParts";
import { Empty, ErrorBox, IntervalBar, Loading, StateBadge, Tip } from "../components/ui/ui";
import { fmtDate, fmtMs, fmtPct, fmtScore, fmtTokens, fmtUsd, shortHash } from "../lib/format";
import { useDocumentTitle } from "../lib/hooks";
import { categoryLabel } from "../lib/labels";

export function LeaderboardPage() {
  useDocumentTitle("Leaderboard");
  const [params, setParams] = useSearchParams();
  const track = params.get("track") ?? "standard";
  const profile = params.get("profile") ?? "";
  const meta = useMeta();
  const lb = useLeaderboard(track, profile || undefined);
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v); else p.delete(k);
    setParams(p, { replace: true });
  };
  return (
    <div className="stack fade-in">
      <div className="page-head">
        <div>
          <h1>Leaderboard</h1>
          <p>
            The latest complete, eligible run per model, endpoint and profile — never the best of several attempts.
            Suite 1 contains one benchmark, so the overall score is the Shadow Twins score.
          </p>
        </div>
        <div className="row">
          <div className="seg" role="group" aria-label="Track">
            <button type="button" aria-pressed={track === "standard"} onClick={() => set("track", "standard")}>Standard</button>
            <button type="button" aria-pressed={track === "repeated"} onClick={() => set("track", "repeated")}>Repeated ×3</button>
          </div>
          <select className="input" style={{ width: 190 }} aria-label="Profile" value={profile} onChange={(e) => set("profile", e.target.value)}>
            <option value="">All profiles</option>
            {meta.data?.profiles.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
        </div>
      </div>
      {lb.isLoading && <Loading />}
      {lb.error && <ErrorBox error={lb.error} />}
      {lb.data && lb.data.rows.length === 0 && (
        <div className="card">
          <Empty title="No eligible ranked runs yet"
            action={<Link to="/" className="btn primary">Evaluate a model</Link>}>
            A run is listed when it used the ranked pack, a real (non-mock) model with a pinned provider endpoint and
            known pricing, completed every item, and the provider reported on each response matched the pin.
          </Empty>
        </div>
      )}
      {lb.data && lb.data.rows.length > 0 && (
        <div className="card table-wrap">
          <table className="data lb">
            <thead>
              <tr>
                <th className="r">#</th><th>Model</th><th>Profile</th><th className="r">Overall</th><th style={{ minWidth: 140 }}>95% interval</th>
                <th className="r">T1</th><th className="r">T2</th><th className="r">T3</th>
                <th className="r"><Tip content="Share of answers that were legal"><span>Valid</span></Tip></th>
                <th className="r hide-sm"><Tip content="Mean score over valid answers only"><span>If valid</span></Tip></th>
                <th className="r hide-sm">Items</th><th className="r hide-sm">Cost</th><th className="r hide-sm">Latency</th>
                <th className="hide-sm">Evaluated</th>
              </tr>
            </thead>
            <tbody>
              {lb.data.rows.map((r) => (
                <tr key={r.run_id}>
                  <td className="r num"><span className="rank">{r.rank}</span></td>
                  <td>
                    <Link to={`/models/${encodeURIComponent(r.model_id)}`}><strong>{r.model_name}</strong></Link>
                    <div className="xsmall faint mono">{r.model_id} · {r.provider_name ?? r.endpoint}</div>
                  </td>
                  <td className="small">{r.profile_id}</td>
                  <td className="r num"><strong style={{ fontSize: "1.05rem" }}>{fmtScore(r.overall)}</strong></td>
                  <td><IntervalBar value={r.overall} interval={r.interval_95} /></td>
                  {["T1", "T2", "T3"].map((t) => <td key={t} className="r num small">{fmtScore(r.tiers[t])}</td>)}
                  <td className="r num small">{fmtPct(r.valid_rate)}</td>
                  <td className="r num small hide-sm">{fmtScore(r.conditional_quality)}</td>
                  <td className="r num small hide-sm">{r.completed}/{r.scheduled}</td>
                  <td className="r num small hide-sm">{fmtUsd(r.cost_usd)}</td>
                  <td className="r num small hide-sm">{fmtMs(r.latency_ms)}</td>
                  <td className="small dim hide-sm">
                    <Link to={`/runs/${encodeURIComponent(r.run_id)}`}>{fmtDate(r.evaluated_at)}</Link>
                    <div className="xsmall faint mono">{r.suite_version} · {shortHash(r.pack_hash)}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="xsmall faint">
        Intervals resample instances within each tier (repetitions stay together); they describe this pack's sampling
        design, not a universal capability guarantee. Cost and latency are shown for context and never affect scores.
      </p>
    </div>
  );
}

export function ModelPage() {
  const { modelId = "" } = useParams();
  const id = decodeURIComponent(modelId);
  const d = useModelDetail(id);
  const [sel, setSel] = useState(0);
  useDocumentTitle(id);
  if (d.isLoading) return <Loading />;
  if (d.error || !d.data) return <ErrorBox error={d.error} />;
  const m = d.data;
  const latest = m.latest_eligible[sel];
  const hist = m.score_histogram as { bins: string[]; counts: number[] } | null;
  const max = hist ? Math.max(1, ...hist.counts) : 1;
  const usage = (m.usage ?? {}) as Record<string, number | null>;
  const model = m.model as { name?: string; context_length?: number } | null;
  return (
    <div className="stack fade-in">
      <div className="page-head">
        <div>
          <div className="row small dim" style={{ marginBottom: 6 }}><Link to="/leaderboard">Leaderboard</Link> / model</div>
          <h1>{model?.name ?? id}</h1>
          <p className="mono small">{id}</p>
        </div>
        <Link to="/" className="btn">Evaluate again</Link>
      </div>
      {m.runs.length === 0 && <div className="card"><Empty title="No runs for this model yet" /></div>}
      {m.latest_eligible.length > 0 && (
        <>
          {m.latest_eligible.length > 1 && (
            <div className="seg" role="group" aria-label="Eligible configurations">
              {m.latest_eligible.map((r, k) => (
                <button key={r.run_id} type="button" aria-pressed={k === sel} onClick={() => setSel(k)}>
                  {r.profile_id} · {r.track}
                </button>
              ))}
            </div>
          )}
          {latest && <ScoreCard run={latest} />}
        </>
      )}
      {m.runs.length > 0 && (
        <div className="grid-2">
          <section className="card card-body stack-s">
            <h2>Answer categories (all runs)</h2>
            <div className="cat-list">
              {Object.entries(m.categories).sort((a, b) => b[1] - a[1]).map(([c, n]) => (
                <span key={c} className={`badge ${c === "valid" ? "ok" : "bad"}`}>{c === "valid" ? "✓" : "✕"} {categoryLabel(c)} · {n}</span>
              ))}
            </div>
            {hist && (
              <>
                <h3 style={{ marginTop: 10 }}>Score distribution (non-mock evaluations)</h3>
                <div className="hist" role="img" aria-label={`score histogram: ${hist.bins.map((b, k) => `${b}: ${hist.counts[k]}`).join(", ")}`}>
                  {hist.counts.map((c, k) => (
                    <div key={k} className="hist-col">
                      <span className="hist-bar" style={{ height: `${(100 * c) / max}%` }} />
                      <span className="xsmall faint">{hist.bins[k].split("-")[0]}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
            <dl className="kv" style={{ marginTop: 8 }}>
              <dt>Responses</dt><dd className="num">{usage.n ?? 0}</dd>
              <dt>Mean tokens in / out</dt><dd className="num">{fmtTokens(usage.p ? Math.round(usage.p) : null)} / {fmtTokens(usage.c ? Math.round(usage.c) : null)}</dd>
              <dt>Mean reasoning tokens</dt><dd className="num">{fmtTokens(usage.r ? Math.round(usage.r) : null)}</dd>
              <dt>Mean latency</dt><dd className="num">{fmtMs(usage.l)}</dd>
              <dt>Total cost</dt><dd className="num">{fmtUsd(usage.cost)}</dd>
            </dl>
          </section>
          <section className="card">
            <div className="card-head"><h2>Run history</h2><span className="xsmall faint">every run, including unranked</span></div>
            <div className="table-wrap">
              <table className="data">
                <thead><tr><th>Run</th><th>Track</th><th>State</th><th className="r">Score</th><th className="r">Valid</th><th>Listed</th></tr></thead>
                <tbody>
                  {m.runs.map((r) => (
                    <tr key={r.run_id}>
                      <td><Link className="mono xsmall" to={`/runs/${encodeURIComponent(r.run_id)}`}>{r.run_id}</Link>
                        <div className="xsmall faint">{fmtDate(r.created_at)}{r.is_mock ? " · mock" : ""}</div></td>
                      <td className="small">{r.track}<div className="xsmall faint">{r.profile_id}</div></td>
                      <td><StateBadge state={r.state} /></td>
                      <td className="r num">{r.overall !== null ? fmtScore(r.overall) : <span className="faint">{fmtScore(r.provisional_overall)}*</span>}</td>
                      <td className="r num small">{fmtPct(r.valid_rate)}</td>
                      <td className="small">{r.leaderboard_eligible ? <span className="ok-text">✓ eligible</span>
                        : <Tip content={r.ineligible_reasons.join("; ")}><span className="faint">no ⓘ</span></Tip>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
