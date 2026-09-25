import { useMutation } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useInstance } from "../api/hooks";
import type { Cell, EditableCellInfo, EntranceInfo, GridState, OutcomeView } from "../api/types";
import { Comparison } from "../components/inspect/Comparison";
import { Layers2D } from "../components/inspect/panels";
import { createViewStore, ViewStoreContext } from "../components/inspect/store";
import { VoxelView } from "../components/inspect/VoxelView";
import { ErrorBox, Loading } from "../components/ui/ui";
import { index, projections } from "../lib/geometry";
import { fmtScore } from "../lib/format";
import { hasWebGL, useDocumentTitle } from "../lib/hooks";
import { categoryLabel } from "../lib/labels";
import { Collapse, EvidencePanels } from "./InstancePage";

/** Geometry-only state for the pre-submission preview (no connectivity claims are made client-side). */
function previewState(occupancy: string): GridState {
  return {
    occupancy, silhouettes: projections(occupancy), empty_components: [], other_empty_cells: [],
    solid_components: [], entrance_component: [], paths: [],
  };
}

export function PracticePage() {
  const { instanceId = "" } = useParams();
  const inst = useInstance(instanceId);
  const [remove, setRemove] = useState<number[]>([]);
  const [add, setAdd] = useState<number[]>([]);
  const store = useMemo(() => createViewStore({ labels: false }), []);
  const submit = useMutation({ mutationFn: () => api.submitPractice(instanceId, { remove, add }) });
  useDocumentTitle("Practice puzzle");

  const data = inst.data;
  const derived = useMemo(() => {
    if (!data) return null;
    const core = data.instance.core;
    const editable: EditableCellInfo[] = core.editable.map((c, id) => ({
      id, cell: c as Cell, originally_solid: core.occupancy[index(c[0], c[1], c[2])] === "1",
    }));
    const entrances: EntranceInfo[] = core.entrances.map((c, k) => ({ index: k, label: "ABCDEFGH"[k], cell: c as Cell }));
    return { core, editable, entrances };
  }, [data]);

  if (inst.isLoading) return <Loading />;
  if (inst.error || !data || !derived) return <ErrorBox error={inst.error ?? "not found"} />;
  const { core, editable, entrances } = derived;

  const requested = (() => {
    const chars = core.occupancy.split("");
    for (const id of remove) { const c = editable[id].cell; chars[index(c[0], c[1], c[2])] = "0"; }
    for (const id of add) { const c = editable[id].cell; chars[index(c[0], c[1], c[2])] = "1"; }
    return chars.join("");
  })();
  const pendingOutcome = {
    removed: remove.map((id) => editable[id].cell), added: add.map((id) => editable[id].cell),
  } as unknown as OutcomeView;
  const toggle = (id: number) => {
    if (submit.data) return;
    const e = editable[id];
    if (e.originally_solid) setRemove((r) => (r.includes(id) ? r.filter((x) => x !== id) : [...r, id]));
    else setAdd((a) => (a.includes(id) ? a.filter((x) => x !== id) : [...a, id]));
  };
  const reset = () => { setRemove([]); setAdd([]); submit.reset(); };
  const result = submit.data;
  const answerJson = JSON.stringify({ remove: [...remove].sort((a, b) => a - b), add: [...add].sort((a, b) => a - b) });

  return (
    <div className="stack fade-in">
      <div className="page-head">
        <div>
          <div className="row small dim" style={{ marginBottom: 6 }}><Link to="/practice">Practice</Link> / <span className="mono">{instanceId}</span></div>
          <h1>Practice puzzle <span className="badge">{data.tier}</span> <span className="badge">unranked</span></h1>
          <p>
            Move up to <strong>{core.budget}</strong> cube{core.budget > 1 ? "s" : ""}: click an editable solid cell to empty it and an
            editable empty cell to fill it. Keep all three shadows and one connected solid; change as many entrance
            links as you can.
          </p>
        </div>
      </div>

      {!result && (
        <div className="practice-editor">
          <ViewStoreContext.Provider value={store}>
            {hasWebGL() ? (
              <VoxelView title="Your object (preview)" state={previewState(requested)} outcome={pendingOutcome}
                entrances={entrances} editable={editable} store={store} active />
            ) : (
              <div className="voxel-view"><div className="voxel-view-head"><h3>Your object (preview)</h3></div>
                <Layers2D state={previewState(requested)} entrances={entrances} editable={editable} outcome={pendingOutcome} /></div>
            )}
          </ViewStoreContext.Provider>
          <section className="card card-body stack">
            <div className="spread">
              <h2>Edit</h2>
              <span className="small num">remove {remove.length} · add {add.length} · budget {core.budget}</span>
            </div>
            <Layers2D state={previewState(core.occupancy)} entrances={entrances} editable={editable}
              onCellClick={toggle} pendingRemove={remove} pendingAdd={add} title="Original with editable cells" />
            <div className="legend xsmall">
              <span><i className="sw sw-editable" aria-hidden /> editable solid (click to empty)</span>
              <span><i className="sw" style={{ border: "1px dashed #4a5566" }} aria-hidden /> editable empty (click to fill)</span>
              <span>letters = entrances</span>
            </div>
            <div className="stack-s">
              <span className="upper faint">Your answer</span>
              <code className="block mono small" style={{ padding: "8px 10px" }}>{answerJson}</code>
            </div>
            {submit.error && <ErrorBox error={submit.error} title="Submission failed" />}
            <div className="row">
              <button type="button" className="btn primary" onClick={() => submit.mutate()} disabled={submit.isPending}>
                {submit.isPending ? "Scoring…" : "Submit for exact scoring"}
              </button>
              <button type="button" className="btn ghost" onClick={reset} disabled={!remove.length && !add.length}>Clear</button>
            </div>
            <Collapse title="Show the exact text a model receives">
              <pre className="block mono">{data.prompt.messages.map((m) => m.content).join("\n\n")}</pre>
            </Collapse>
          </section>
        </div>
      )}

      {result && (
        <>
          <div className={`banner ${result.evaluation.valid ? "ok" : "bad"}`} role="status">
            <span className="icon">{result.evaluation.valid ? "✓" : "✕"}</span>
            <div>
              <strong>
                {result.evaluation.valid ? `Valid — score ${fmtScore(result.evaluation.score)} / 100`
                  : `Invalid — ${categoryLabel(result.evaluation.category)} (score 0)`}
              </strong>
              <div className="small">
                You changed {result.evaluation.raw_objective ?? 0} pair{result.evaluation.raw_objective === 1 ? "" : "s"}; the certified
                optimum changes {result.evaluation.max_objective}. Practice results are never ranked.
              </div>
            </div>
            <button type="button" className="btn small" style={{ marginLeft: "auto" }} onClick={reset}>Try again</button>
          </div>
          <Comparison replay={result.replay} modelLabel="You" />
          <EvidencePanels replay={result.replay} />
        </>
      )}
      <p className="xsmall faint">
        Removed cells appear as red outlines, added cells in teal. Entrances:{" "}
        {entrances.map((e) => `${e.label} (${e.cell.join(",")})`).join(" · ")}.
      </p>
    </div>
  );
}
