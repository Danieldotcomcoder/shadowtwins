import * as Collapsible from "@radix-ui/react-collapsible";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useJob, useReplay } from "../api/hooks";
import type { Attempt, EditableCellInfo, JobDetail, ShadowTwinsReplay } from "../api/types";
import { Comparison } from "../components/inspect/Comparison";
import { ChecksList, ScoreArithmetic } from "../components/inspect/panels";
import { ErrorBox, Loading, StateBadge } from "../components/ui/ui";
import { fmtMs, fmtScore, fmtTokens, fmtUsd, shortHash } from "../lib/format";
import { useDocumentTitle } from "../lib/hooks";
import { categoryLabel, TIER_NAME } from "../lib/labels";

export function Collapse({ title, children, defaultOpen = false }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} className="collapse">
      <Collapsible.Trigger className="collapse-trigger">
        <span aria-hidden>{open ? "▾" : "▸"}</span> {title}
      </Collapsible.Trigger>
      <Collapsible.Content className="collapse-content">{children}</Collapsible.Content>
    </Collapsible.Root>
  );
}

export function EditTable({ edit, editable }: { edit: { remove: number[]; add: number[] } | null; editable: EditableCellInfo[] }) {
  if (!edit) return <p className="small dim">No edit could be parsed.</p>;
  const cell = (id: number) => {
    const e = editable.find((x) => x.id === id);
    return e ? `(${e.cell.join(",")})` : "out of range";
  };
  return (
    <div className="edit-table">
      <div><span className="upper faint">remove</span>
        {edit.remove.length ? edit.remove.map((id, k) => <div key={k} className="mono small"><span className="rm-dot" aria-hidden />#{id} {cell(id)}</div>)
          : <div className="small faint">none</div>}</div>
      <div><span className="upper faint">add</span>
        {edit.add.length ? edit.add.map((id, k) => <div key={k} className="mono small"><span className="add-dot" aria-hidden />#{id} {cell(id)}</div>)
          : <div className="small faint">none</div>}</div>
    </div>
  );
}

function AttemptRow({ a }: { a: Attempt }) {
  return (
    <li className="attempt">
      <div className="spread">
        <span className="small"><strong>Attempt {a.number}</strong> · {a.state}{a.error_category ? ` · ${a.error_category}` : ""}</span>
        <span className="xsmall faint mono">{a.generation_id ?? ""}</span>
      </div>
      <div className="xsmall dim">
        {a.provider_name ?? "provider ?"} · {a.response_model ?? "model ?"} · finish {a.finish_reason ?? "—"}
        {a.native_finish_reason && a.native_finish_reason !== a.finish_reason ? ` (${a.native_finish_reason})` : ""}
        {" · "}{fmtTokens(a.prompt_tokens)} in / {fmtTokens(a.completion_tokens)} out
        {a.reasoning_tokens ? ` (${fmtTokens(a.reasoning_tokens)} reasoning)` : ""} · {fmtUsd(a.cost_usd)} {a.cost_source ?? ""} · {fmtMs(a.latency_ms)}
      </div>
      {a.error_message && <div className="xsmall bad-text">{a.error_message}</div>}
    </li>
  );
}

export function EvidencePanels({ replay, job }: { replay: ShadowTwinsReplay; job?: JobDetail }) {
  const model = replay.model;
  const answered = job?.attempts.filter((a) => a.state === "response").slice(-1)[0];
  return (
    <div className="grid-2">
      <section className="card card-body stack" aria-labelledby="answer-title">
        <h2 id="answer-title">Answer</h2>
        {answered && (
          <div className="stack-s">
            <span className="upper faint">Raw response</span>
            <pre className="block mono">{answered.content || "(empty)"}</pre>
            {answered.refusal && <p className="small">Provider refusal: {answered.refusal}</p>}
          </div>
        )}
        {model && (
          <>
            <div className="stack-s">
              <span className="upper faint">Parsed edit</span>
              <EditTable edit={model.edit} editable={replay.editable} />
            </div>
            <div className="stack-s">
              <span className="upper faint">Validity checks (in evaluation order)</span>
              <ChecksList checks={model.checks} />
            </div>
          </>
        )}
      </section>
      <div className="stack">
        {model && (
          <section className="card card-body stack-s" aria-labelledby="arith-title">
            <h2 id="arith-title">Score arithmetic</h2>
            <ScoreArithmetic outcome={model} verified={job?.certificate_verified} />
          </section>
        )}
        <section className="card card-body stack-s" aria-labelledby="cert-title">
          <h2 id="cert-title">Certification</h2>
          <dl className="kv">
            <dt>Certified optimum</dt><dd>v* = {replay.optimal.v_star} (exhaustive enumeration)</dd>
            <dt>Certificate</dt><dd className="mono xsmall">{shortHash(replay.certificate_hash)}
              {job && (job.certificate_verified ? <span className="badge ok" style={{ marginLeft: 6 }}>✓ independently verified</span>
                : <span className="badge warn" style={{ marginLeft: 6 }}>not verified</span>)}</dd>
            <dt>Instance hash</dt><dd className="mono xsmall">{shortHash(replay.instance_hash)}</dd>
            <dt>Evaluator</dt><dd className="mono xsmall">{replay.evaluator_version} · {replay.replay_version}</dd>
            <dt>Optimal witness</dt><dd><EditTable edit={replay.optimal.edit} editable={replay.editable} /></dd>
          </dl>
        </section>
        {job && (
          <section className="card card-body stack-s" aria-labelledby="att-title">
            <h2 id="att-title">Attempts</h2>
            <ol className="plain-list stack-s">{job.attempts.map((a) => <AttemptRow key={a.attempt_id} a={a} />)}</ol>
            <Collapse title="Prompt sent to the model">
              <pre className="block mono">{job.prompt.messages.map((m) => m.content).join("\n\n")}</pre>
              <p className="xsmall faint">Protocol {job.prompt.protocol_version} · {shortHash(job.prompt.text_hash)}</p>
            </Collapse>
          </section>
        )}
      </div>
    </div>
  );
}

export function InstancePage() {
  const { runId = "", jobId = "" } = useParams();
  const job = useJob(runId, Number(jobId));
  const replay = useReplay(job.data?.instance_id, runId, Number(jobId));
  useDocumentTitle(job.data ? `Inspect · ${job.data.instance_id}` : "Inspect");
  if (job.isLoading || (job.data && replay.isLoading)) return <Loading label="Loading instance" />;
  if (job.error) return <ErrorBox error={job.error} title="Item not found" />;
  if (replay.error) return <ErrorBox error={replay.error} title="No evaluation for this item" />;
  if (!job.data || !replay.data) return null;
  const d = job.data;
  const r = replay.data;
  const m = r.model;
  return (
    <div className="stack fade-in">
      <div className="page-head">
        <div>
          <div className="row small dim" style={{ marginBottom: 6 }}>
            <Link to="/runs">Runs</Link> / <Link to={`/runs/${encodeURIComponent(runId)}`} className="mono">{runId}</Link> / <span className="mono">{d.instance_id}</span>
          </div>
          <h1 className="row" style={{ gap: 12 }}>
            <span className="mono" style={{ fontSize: "0.8em" }}>{d.instance_id}</span>
            {m && (m.valid ? <span className="badge ok">✓ valid · {fmtScore(m.score)}</span>
              : <span className="badge bad">✕ {categoryLabel(m.category)} · 0</span>)}
          </h1>
          <p>{TIER_NAME[d.tier] ?? d.tier} · budget {r.budget} relocation{r.budget > 1 ? "s" : ""} · {r.entrances.length} entrances
            · {r.editable.length} editable cells · repetition {d.job.repetition} · <StateBadge state={d.job.state} /></p>
        </div>
      </div>
      <Comparison replay={r} modelLabel="Model" />
      <EvidencePanels replay={r} job={d} />
    </div>
  );
}
