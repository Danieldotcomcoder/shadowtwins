import * as Slider from "@radix-ui/react-slider";
import * as Switch from "@radix-ui/react-switch";
import * as Tabs from "@radix-ui/react-tabs";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Cell, ShadowTwinsReplay } from "../../api/types";
import { hasWebGL, useInView, useMediaQuery, usePrefersReducedMotion } from "../../lib/hooks";
import { fmtScore } from "../../lib/format";
import { categoryLabel } from "../../lib/labels";
import { Layers2D, PairMatrix, SilhouettePanels } from "./panels";
import { createViewStore, useView, useViewStore, ViewStoreContext, type ViewStore } from "./store";
import { VoxelView } from "./VoxelView";

type Role = "original" | "model" | "optimal";

function offendingCells(checks: { status: string; cells: Cell[] }[] | undefined): Cell[] {
  return (checks ?? []).filter((c) => c.status === "fail").flatMap((c) => c.cells);
}

/** Drives the shared path-animation phase while playing, visible and motion is allowed. */
function usePlayback(store: ViewStore, visible: boolean, reduced: boolean) {
  useEffect(() => {
    if (reduced) {
      store.set({ playing: false });
      return;
    }
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const s = store.get();
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (s.playing && visible && s.selectedPair) store.set({ t: (s.t + dt * 0.35 * s.speed) % 1 });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [store, visible, reduced]);
}

function Toolbar({ mode, setMode, webgl, reduced }: {
  mode: "3d" | "2d"; setMode: (m: "3d" | "2d") => void; webgl: boolean; reduced: boolean;
}) {
  const store = useViewStore();
  const maxLayer = useView((s) => s.maxLayer);
  const transparent = useView((s) => s.transparent);
  const labels = useView((s) => s.labels);
  const editable = useView((s) => s.editable);
  const playing = useView((s) => s.playing);
  const t = useView((s) => s.t);
  const speed = useView((s) => s.speed);
  const pair = useView((s) => s.selectedPair);
  const toggle = (label: string, checked: boolean, on: (v: boolean) => void, disabled = false) => (
    <label className="tb-switch">
      <Switch.Root className="switch" checked={checked} onCheckedChange={on} disabled={disabled} aria-label={label}>
        <Switch.Thumb className="switch-thumb" />
      </Switch.Root>
      <span>{label}</span>
    </label>
  );
  return (
    <div className="toolbar" role="toolbar" aria-label="View controls">
      <div className="seg" role="group" aria-label="Rendering">
        <button type="button" aria-pressed={mode === "3d"} disabled={!webgl} onClick={() => setMode("3d")}
          title={webgl ? "3D views" : "WebGL is unavailable"}>3D</button>
        <button type="button" aria-pressed={mode === "2d"} onClick={() => setMode("2d")}>2D layers</button>
      </div>
      <div className="tb-slice">
        <span className="xsmall dim" id="slice-label">Layers z ≤ {maxLayer}</span>
        <Slider.Root className="slider" min={0} max={3} step={1} value={[maxLayer]}
          onValueChange={([v]) => store.set({ maxLayer: v })} aria-labelledby="slice-label">
          <Slider.Track className="slider-track"><Slider.Range className="slider-range" /></Slider.Track>
          <Slider.Thumb className="slider-thumb" aria-label="Highest visible layer" />
        </Slider.Root>
      </div>
      {mode === "3d" && (
        <>
          {toggle("Transparent", transparent, (v) => store.set({ transparent: v }))}
          {toggle("Cell IDs", labels, (v) => store.set({ labels: v }))}
          {toggle("Editable tint", editable, (v) => store.set({ editable: v }))}
          <button type="button" className="btn small" onClick={() => store.resetCamera()} title="Reset camera (R)">
            ⟲ Reset view
          </button>
        </>
      )}
      <div className="tb-play" role="group" aria-label="Route animation">
        <button type="button" className="btn small icon" disabled={!pair || reduced || mode === "2d"}
          onClick={() => store.set({ playing: !playing })} aria-pressed={playing}
          aria-label={playing ? "Pause route animation" : "Play route animation"}
          title={reduced ? "Animation disabled by reduced-motion preference" : pair ? "Play / pause route" : "Select a pair first"}>
          {playing ? "❚❚" : "▶"}
        </button>
        <Slider.Root className="slider narrow" min={0} max={1} step={0.01} value={[t]} disabled={!pair || mode === "2d"}
          onValueChange={([v]) => store.set({ t: v, playing: false })} aria-label="Scrub route animation">
          <Slider.Track className="slider-track"><Slider.Range className="slider-range" /></Slider.Track>
          <Slider.Thumb className="slider-thumb" aria-label="Route position" />
        </Slider.Root>
        <select className="input tb-speed" value={speed} aria-label="Animation speed" disabled={!pair || mode === "2d"}
          onChange={(e) => store.set({ speed: Number(e.target.value) })}>
          <option value={0.5}>0.5×</option>
          <option value={1}>1×</option>
          <option value={2}>2×</option>
        </select>
      </div>
    </div>
  );
}

interface Column {
  role: Role;
  title: string;
  badge: React.ReactNode;
}

export function Comparison({ replay, modelLabel = "Model", note }: {
  replay: ShadowTwinsReplay;
  modelLabel?: string;
  note?: React.ReactNode;
}) {
  const store = useMemo(() => createViewStore(), []);
  const webgl = useMemo(() => hasWebGL(), []);
  const [mode, setMode] = useState<"3d" | "2d">(webgl ? "3d" : "2d");
  const reduced = usePrefersReducedMotion();
  const narrow = useMediaQuery("(max-width: 900px)");
  const ref = useRef<HTMLDivElement | null>(null);
  const [el, setEl] = useState<HTMLDivElement | null>(null);
  const inView = useInView(el);
  const [tab, setTab] = useState<Role>(replay.model ? "model" : "original");
  usePlayback(store, inView, reduced);

  const model = replay.model;
  const columns: Column[] = [
    { role: "original", title: "Original", badge: <span className="badge">A</span> },
    ...(model ? [{
      role: "model" as const, title: modelLabel,
      badge: model.valid
        ? <span className="badge accent">{fmtScore(model.score)}</span>
        : <span className="badge bad">✕ {categoryLabel(model.category)}</span>,
    }] : []),
    { role: "optimal", title: "Optimal", badge: <span className="badge ok">✓ {fmtScore(replay.optimal.score)}</span> },
  ];

  const pair = useSyncPair(store);
  const renderView = (c: Column) => {
    const outcome = c.role === "original" ? null : c.role === "model" ? model : replay.optimal;
    const state = c.role === "original" ? replay.original : outcome?.final ?? null;
    const offending = c.role === "model" && model && !model.valid ? offendingCells(model.checks) : [];
    const pathCells = pair && state ? state.paths.find((p) => p.i === pair[0] && p.j === pair[1])?.cells : undefined;
    if (mode === "2d") {
      return (
        <div className="voxel-view" key={c.role}>
          <div className="voxel-view-head"><h3>{c.title}</h3>{c.badge}</div>
          <Layers2D state={state} entrances={replay.entrances} editable={replay.editable} outcome={outcome}
            offending={offending} pathCells={pathCells} title={c.title} />
          {c.role === "model" && model && !model.valid && state && (
            <div className="voxel-invalid static" role="note">✕ Invalid answer — shown as requested, not a legal result</div>
          )}
        </div>
      );
    }
    return (
      <VoxelView key={c.role} title={c.title} badge={c.badge} state={state} outcome={outcome}
        entrances={replay.entrances} editable={replay.editable} offending={offending}
        invalid={c.role === "model" && !!model && !model.valid} store={store} active={inView}
        placeholder={c.role === "model" ? "No object could be built from this answer." : undefined} />
    );
  };

  return (
    <ViewStoreContext.Provider value={store}>
      <div className="comparison" ref={(n) => { ref.current = n; setEl(n); }}>
        {note && <div className="banner info" role="note"><span className="icon">i</span><div>{note}</div></div>}
        <Toolbar mode={mode} setMode={setMode} webgl={webgl} reduced={reduced} />
        {!webgl && (
          <div className="banner warn small"><span className="icon">!</span>
            WebGL is unavailable in this browser, so the 2D layer view is shown. All data is identical.</div>
        )}
        {narrow ? (
          <Tabs.Root value={tab} onValueChange={(v) => setTab(v as Role)}>
            <Tabs.List className="seg views-tabs" aria-label="Choose object">
              {columns.map((c) => <Tabs.Trigger key={c.role} value={c.role}>{c.title}</Tabs.Trigger>)}
            </Tabs.List>
            {columns.map((c) => (
              <Tabs.Content key={c.role} value={c.role} className="views single">{renderView(c)}</Tabs.Content>
            ))}
          </Tabs.Root>
        ) : (
          <div className={`views cols-${columns.length}`}>{columns.map(renderView)}</div>
        )}
        <Legend />
        <div className="grid-2 comparison-lower">
          <div className="card card-body">
            <PairMatrix entrances={replay.entrances} original={replay.original}
              outcome={tab === "optimal" || !model ? replay.optimal : model} title={tab === "optimal" || !model ? "Optimal" : modelLabel} />
            {model && (
              <div className="seg" style={{ marginTop: 12 }} role="group" aria-label="Pair matrix source">
                <button type="button" aria-pressed={tab !== "optimal"} onClick={() => setTab("model")}>{modelLabel}</button>
                <button type="button" aria-pressed={tab === "optimal"} onClick={() => setTab("optimal")}>Optimal</button>
              </div>
            )}
          </div>
          <div className="card card-body">
            <div className="spread" style={{ marginBottom: 10 }}>
              <h3>Exact silhouettes</h3>
              <span className="xsmall faint">From evaluator masks · ≠ marks a changed pixel</span>
            </div>
            <SilhouettePanels original={replay.original}
              columns={[...(model ? [{ title: modelLabel, outcome: model }] : []), { title: "Optimal", outcome: replay.optimal }]} />
          </div>
        </div>
      </div>
    </ViewStoreContext.Provider>
  );
}

function useSyncPair(store: ViewStore): [number, number] | null {
  const [pair, setPair] = useState(store.get().selectedPair);
  useEffect(() => store.subscribe(() => setPair(store.get().selectedPair)), [store]);
  return pair;
}

function Legend() {
  const pair = useView((s) => s.selectedPair);
  return (
    <div className="legend small" role="group" aria-label="Legend">
      <span><i className="sw sw-solid" aria-hidden /> solid</span>
      <span><i className="sw sw-editable" aria-hidden /> editable</span>
      <span><i className="sw sw-added" aria-hidden /> added</span>
      <span><i className="sw sw-removed" aria-hidden /> removed (outline)</span>
      <span><i className="sw sw-entrance" aria-hidden /> entrance</span>
      {pair && (
        <>
          <span><i className="sw sw-path" aria-hidden /> route (linked)</span>
          <span><i className="sw sw-region-a" aria-hidden /> cubes: region of first entrance</span>
          <span><i className="sw sw-region-b" aria-hidden /> diamonds: region of second entrance</span>
        </>
      )}
    </div>
  );
}
