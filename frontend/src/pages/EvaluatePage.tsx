import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useCatalog, useEndpoints, useEstimate, useMeta } from "../api/hooks";
import type { RunCreate } from "../api/types";
import { ModelPicker } from "../components/models/ModelPicker";
import { ErrorBox, Loading, MockBadge, SkeletonBlock, Stat, Tip } from "../components/ui/ui";
import { fmtPerMillion, fmtTokens, fmtUsd } from "../lib/format";
import { useDocumentTitle } from "../lib/hooks";

type Mode = "quick_check" | "standard" | "repeated";

const MODES: { id: Mode; title: string; blurb: string; calls: number; ranked: boolean }[] = [
  { id: "quick_check", title: "Quick Check", blurb: "9 practice instances, one pass. Never ranked.", calls: 9, ranked: false },
  { id: "standard", title: "Standard", blurb: "30 ranked instances (10 per tier), one pass.", calls: 30, ranked: true },
  { id: "repeated", title: "Repeated", blurb: "The same 30 instances × 3. Separate track; averaged, never best-of.", calls: 90, ranked: true },
];

export function EvaluatePage() {
  useDocumentTitle("Evaluate");
  const meta = useMeta();
  const catalog = useCatalog();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [modelId, setModelId] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("quick_check");
  const [profileId, setProfileId] = useState("standard");
  const [endpoint, setEndpoint] = useState<string>("");
  const [limit, setLimit] = useState("2.00");
  const [concurrency, setConcurrency] = useState(2);
  const [allowUnknown, setAllowUnknown] = useState(false);
  const endpoints = useEndpoints(modelId);
  const model = catalog.data?.models.find((m) => m.model_id === modelId) ?? null;
  const operator = meta.data?.auth?.operator === true;
  const groqPlan = (meta.data?.providers?.groq as { plan?: string } | undefined)?.plan;

  useEffect(() => {
    setEndpoint("");
    setAllowUnknown(false);
  }, [modelId]);

  const spec: RunCreate | null = useMemo(() => {
    const l = Number(limit);
    if (!modelId || !(l > 0)) return null;
    return {
      model_id: modelId, profile_id: profileId, mode, spend_limit_usd: l, concurrency,
      provider: endpoint || null, allow_unknown_pricing: allowUnknown,
    };
  }, [modelId, profileId, mode, limit, concurrency, endpoint, allowUnknown]);
  const [debounced, setDebounced] = useState<RunCreate | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(spec), 250);
    return () => clearTimeout(t);
  }, [spec]);
  const plan = useEstimate(debounced);

  const favorite = useMutation({
    mutationFn: ({ id, on }: { id: string; on: boolean }) => api.setFavorite(id, on),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["catalog"] }),
  });
  const create = useMutation({
    mutationFn: (s: RunCreate) => api.createRun(s),
    onSuccess: (run) => {
      qc.invalidateQueries({ queryKey: ["runs"] });
      navigate(`/runs/${encodeURIComponent(run.run_id)}`);
    },
  });

  const profiles = meta.data?.profiles ?? [];
  const est = plan.data?.estimate;
  const blocking = plan.data?.blocking ?? [];
  const canStart = !!spec && !!plan.data && blocking.length === 0 && operator && !create.isPending && !plan.isFetching;

  return (
    <div className="stack fade-in">
      <div className="page-head">
        <div>
          <h1>Evaluate a model</h1>
          <p>
            Pick a model from OpenRouter or Groq, choose how thoroughly to test it, and check the cost before anything
            is sent.
            Every answer is scored exactly against a certified optimum — <Link to="/about">how scoring works</Link>.
          </p>
        </div>
      </div>

      <div className="eval-grid">
        <div className="stack">
          <section className="card" aria-labelledby="step-model">
            <div className="card-head">
              <h2 id="step-model"><span className="step">1</span> Model</h2>
              {catalog.data && (
                <span className="xsmall faint">
                  {Object.entries(catalog.data.snapshots).map(([p, s]) => `${p}: ${s.model_count}${s.stale ? " (stale)" : ""}`).join(" · ")}
                </span>
              )}
            </div>
            <div className="card-body">
              {catalog.isLoading && <SkeletonBlock h={320} />}
              {catalog.error && <ErrorBox error={catalog.error} title="Could not load the model catalog" />}
              {catalog.data && Object.keys(catalog.data.errors).length > 0 && (
                <div className="banner warn small" style={{ marginBottom: 10 }}>
                  <span className="icon">!</span>
                  <div>Catalog refresh failed ({Object.entries(catalog.data.errors).map(([k, v]) => `${k}: ${v}`).join("; ")}).
                    Showing the last stored snapshot.</div>
                </div>
              )}
              {catalog.data && (
                <ModelPicker models={catalog.data.models} favorites={catalog.data.favorites} recents={catalog.data.recents}
                  value={modelId} onChange={setModelId} profileId={profileId}
                  onToggleFav={operator ? (id, on) => favorite.mutate({ id, on }) : undefined} />
              )}
            </div>
          </section>

          <section className="card" aria-labelledby="step-setup">
            <div className="card-head"><h2 id="step-setup"><span className="step">2</span> Run setup</h2></div>
            <div className="card-body stack">
              <div className="field">
                <span className="label" id="mode-label">Mode</span>
                <div className="grid-3" role="radiogroup" aria-labelledby="mode-label">
                  {MODES.map((m) => (
                    <button key={m.id} type="button" role="radio" aria-checked={mode === m.id} className="choice"
                      onClick={() => setMode(m.id)}>
                      <span className="spread"><strong>{m.title}</strong>
                        <span className={`badge ${m.ranked ? "accent" : ""}`}>{m.calls} calls</span></span>
                      <span className="xsmall dim">{m.blurb}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="field">
                <span className="label" id="profile-label">Generation profile</span>
                <div className="grid-3" role="radiogroup" aria-labelledby="profile-label">
                  {profiles.map((p) => {
                    const compat = model?.compat?.find((c) => c.profile_id === p.id);
                    return (
                      <button key={p.id} type="button" role="radio" aria-checked={profileId === p.id} className="choice"
                        onClick={() => setProfileId(p.id)}>
                        <span className="spread"><strong>{p.label}</strong>
                          {compat && (compat.compatible ? <span className="badge ok">✓</span>
                            : <span className="badge bad" title={compat.problems.join("; ")}>✕</span>)}</span>
                        <span className="xsmall dim">{fmtTokens(p.max_tokens)} output tokens · {p.reasoning ? `effort ${String((p.reasoning as { effort?: string }).effort)}` : "model default reasoning"}</span>
                      </button>
                    );
                  })}
                </div>
                {profiles.find((p) => p.id === profileId) && (
                  <p className="xsmall faint">{profiles.find((p) => p.id === profileId)!.enforcement}</p>
                )}
              </div>

              <div className="grid-3">
                {model?.provider === "groq" ? (
                  <div className="field">
                    <span className="label">Provider</span>
                    <span className="small">Groq, directly</span>
                    <span className="xsmall faint">
                      Groq serves its own models: no endpoint to pin, no fallbacks.
                      {groqPlan === "free" && " Free plan: $0, but each model has daily limits; runs wait for the reset."}
                    </span>
                  </div>
                ) : (
                  <div className="field">
                    <label htmlFor="endpoint">Provider endpoint</label>
                    <select id="endpoint" className="input" value={endpoint} onChange={(e) => setEndpoint(e.target.value)}
                      disabled={!modelId || endpoints.isLoading}>
                      <option value="">Not pinned (unranked, fallbacks allowed)</option>
                      {endpoints.data?.endpoints.map((e) => (
                        <option key={e.slug} value={e.slug}>
                          {e.provider_name} · {e.slug}{e.quantization && e.quantization !== "unknown" ? ` · ${e.quantization}` : ""} ·
                          {" "}{fmtPerMillion(e.pricing.prompt)}/{fmtPerMillion(e.pricing.completion)}
                        </option>
                      ))}
                    </select>
                    <span className="xsmall faint">Ranked runs pin one endpoint and disable fallbacks.</span>
                  </div>
                )}
                <div className="field">
                  <label htmlFor="limit">Spending limit (USD)</label>
                  <input id="limit" className="input num" inputMode="decimal" value={limit}
                    onChange={(e) => setLimit(e.target.value.replace(/[^0-9.]/g, ""))} />
                  <span className="xsmall faint">Dispatch stops before a call could exceed it.</span>
                </div>
                <div className="field">
                  <label htmlFor="concurrency">Concurrent requests</label>
                  <input id="concurrency" className="input num" type="number" min={1} max={16} value={concurrency}
                    onChange={(e) => setConcurrency(Math.max(1, Math.min(16, Number(e.target.value) || 1)))} />
                </div>
              </div>
              {model && !model.pricing_known && (
                <label className="row small">
                  <input type="checkbox" checked={allowUnknown} onChange={(e) => setAllowUnknown(e.target.checked)} />
                  Pricing is unknown for this model. Run anyway as an <strong>unranked</strong> evaluation with no
                  enforceable spending limit.
                </label>
              )}
            </div>
          </section>
        </div>

        <aside className="card eval-summary" aria-labelledby="summary-title">
          <div className="card-head"><h2 id="summary-title"><span className="step">3</span> Review and start</h2></div>
          <div className="card-body stack">
            {!model && <p className="dim small">Choose a model to see the estimate.</p>}
            {model && (
              <div className="stack-s">
                <div className="row"><strong>{model.name}</strong>{model.is_mock && <MockBadge />}</div>
                {operator && (
                  <button type="button" className="btn ghost small" style={{ alignSelf: "flex-start", paddingLeft: 0 }}
                    aria-pressed={!!catalog.data?.favorites.includes(model.model_id)}
                    onClick={() => favorite.mutate({ id: model.model_id, on: !catalog.data?.favorites.includes(model.model_id) })}>
                    {catalog.data?.favorites.includes(model.model_id) ? "★ Favourite" : "☆ Add to favourites"}
                  </button>
                )}
                <span className="mono xsmall faint">{model.model_id}</span>
              </div>
            )}
            {plan.isFetching && !plan.data && <Loading label="Estimating" />}
            {plan.error && <ErrorBox error={plan.error} title="Cannot plan this run" />}
            {plan.data && est && (
              <>
                <div className="stats">
                  <Stat k="Calls" v={est.calls} />
                  <Stat k="Typical cost" v={fmtUsd(est.typical_usd)} hint={`~${fmtTokens(Number(est.assumptions.typical_output_tokens))} output tokens per call`} />
                  <Stat k="Worst case" v={fmtUsd(est.worst_case_usd)} hint="every call uses its full budget" />
                  <Stat k="Per-call reserve" v={fmtUsd(est.max_per_call_usd)} />
                </div>
                <div className={`banner ${plan.data.ranked ? "ok" : "info"}`}>
                  <span className="icon">{plan.data.ranked ? "✓" : "i"}</span>
                  <div>
                    <strong>{plan.data.ranked ? "Ranked-eligible run" : "Unranked run"}</strong>
                    {!plan.data.ranked && (
                      <ul className="plain-list small">
                        {plan.data.not_ranked_reasons.map((r) => <li key={r}>{r}</li>)}
                      </ul>
                    )}
                    {plan.data.ranked && <div className="small">Listed on the leaderboard once every item completes.</div>}
                  </div>
                </div>
                {blocking.length > 0 && (
                  <div className="banner bad" role="alert">
                    <span className="icon">✕</span>
                    <div><strong>Cannot start</strong>
                      <ul className="plain-list small">{blocking.map((b) => <li key={b}>{b}</li>)}</ul></div>
                  </div>
                )}
                {plan.data.compatibility.warnings.length > 0 && (
                  <ul className="plain-list xsmall faint">{plan.data.compatibility.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
                )}
              </>
            )}
            {create.error && <ErrorBox error={create.error} title="Run was not created" />}
            {operator ? (
              <button type="button" className="btn primary" disabled={!canStart} onClick={() => spec && create.mutate(spec)}>
                {create.isPending ? "Starting…" : "Start evaluation"}
              </button>
            ) : (
              <Tip content="Starting runs requires operator access (see the Viewer badge in the header).">
                <span><button type="button" className="btn primary" disabled style={{ width: "100%" }}>Start evaluation</button></span>
              </Tip>
            )}
            <p className="xsmall faint">
              Runs continue on the server if you close this tab. Pause, resume and cancel from the run page.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
