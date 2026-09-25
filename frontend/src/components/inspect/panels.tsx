/* 2D inspection panels. Everything is drawn from authoritative evaluator/replay data; nothing
   here computes validity or scores. */

import type { Cell, Check, EditableCellInfo, EntranceInfo, GridState, OutcomeView, PairStatus, Rows } from "../../api/types";
import { AXES, N, cellKey, solidSet } from "../../lib/geometry";
import { CHECK_LABEL, categoryLabel } from "../../lib/labels";
import { useView, useViewStore } from "./store";

/* ---- silhouettes ------------------------------------------------------------------------ */

export function SilhouetteGrid({
  rows, mismatch, axis, caption,
}: { rows: Rows; mismatch?: Rows | null; axis: "x" | "y" | "z"; caption: string }) {
  const a = AXES[axis];
  // Views along x and y are drawn with z up (v = 3 on top); the top view keeps y = 0 on top,
  // matching the printed row order of the prompt.
  const vOrder = axis === "z" ? [0, 1, 2, 3] : [3, 2, 1, 0];
  const size = 17;
  const gap = 2;
  const w = N * size + (N - 1) * gap;
  const lost: string[] = [];
  const gained: string[] = [];
  return (
    <figure className="sil">
      <svg width={w} height={w} viewBox={`0 0 ${w} ${w}`} role="img" aria-label={`${caption}, ${a.title}`}>
        <defs>
          <pattern id="hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="2" height="4" fill="rgba(242,122,122,0.55)" />
          </pattern>
        </defs>
        {vOrder.map((v, r) =>
          [0, 1, 2, 3].map((u) => {
            const on = rows[v][u] === 1;
            const bad = mismatch?.[v]?.[u] === 1;
            if (bad) (on ? gained : lost).push(`${a.u}=${u},${a.v}=${v}`);
            const x = u * (size + gap);
            const y = r * (size + gap);
            return (
              <g key={`${u}-${v}`}>
                <rect x={x} y={y} width={size} height={size} rx={2.5}
                  fill={on ? "#cfd6e2" : "#1b2027"} stroke={bad ? "#f27a7a" : "#2a313b"} strokeWidth={bad ? 2 : 1} />
                {bad && <rect x={x} y={y} width={size} height={size} rx={2.5} fill="url(#hatch)" />}
                {bad && (
                  <text x={x + size / 2} y={y + size / 2 + 4} textAnchor="middle" fontSize="11" fontWeight="700"
                    fill={on ? "#7a1f1f" : "#f27a7a"}>≠</text>
                )}
              </g>
            );
          }),
        )}
      </svg>
      <figcaption className="xsmall faint">
        {caption}
        {(lost.length > 0 || gained.length > 0) && (
          <span className="sr-only">
            {lost.length ? ` Lost pixels: ${lost.join("; ")}.` : ""}
            {gained.length ? ` Gained pixels: ${gained.join("; ")}.` : ""}
          </span>
        )}
      </figcaption>
    </figure>
  );
}

export function SilhouettePanels({ original, columns }: {
  original: GridState;
  columns: { title: string; outcome: OutcomeView | null }[];
}) {
  return (
    <div className="sil-table" role="table" aria-label="Exact silhouettes">
      <div className="sil-row sil-headrow" role="row">
        <div role="columnheader" className="sil-axis" />
        <div role="columnheader" className="upper faint">Original</div>
        {columns.map((c) => <div key={c.title} role="columnheader" className="upper faint">{c.title}</div>)}
      </div>
      {(["x", "y", "z"] as const).map((axis) => (
        <div className="sil-row" role="row" key={axis}>
          <div role="rowheader" className="sil-axis">
            <strong>{AXES[axis].title}</strong>
            <span className="xsmall faint">{AXES[axis].u} → · {AXES[axis].v} {axis === "z" ? "↓" : "↑"}</span>
          </div>
          <div role="cell"><SilhouetteGrid axis={axis} rows={original.silhouettes[axis]} caption="Original" /></div>
          {columns.map((c) => (
            <div role="cell" key={c.title}>
              {c.outcome?.final ? (
                <SilhouetteGrid axis={axis} rows={c.outcome.final.silhouettes[axis]}
                  mismatch={c.outcome.silhouette_mismatch?.[axis]} caption={c.title} />
              ) : (
                <div className="sil-missing xsmall faint">no object</div>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

/* ---- pair matrix -------------------------------------------------------------------------- */

const CHANGE_ICON = { opened: "↗", closed: "✕", unchanged: "" } as const;

export function PairMatrix({ entrances, original, outcome, title }: {
  entrances: EntranceInfo[];
  original: GridState;
  outcome: OutcomeView | null;
  title: string;
}) {
  const store = useViewStore();
  const selected = useView((s) => s.selectedPair);
  const byPair = new Map<string, PairStatus>();
  for (const p of outcome?.pairs ?? []) byPair.set(`${p.i}-${p.j}`, p);
  const comp = original.entrance_component;
  const linkedOriginal = (i: number, j: number) => comp[i] !== -1 && comp[i] === comp[j];
  const k = entrances.length;
  const valid = !!outcome?.valid;
  return (
    <div className="pair-matrix">
      <div className="spread">
        <h3>Entrance pairs · {title}</h3>
        <span className="xsmall faint">Select a pair to trace its route or its separating regions</span>
      </div>
      {!valid && outcome && (
        <p className="small dim" style={{ marginTop: 6 }}>
          Invalid answers change no pairs in the scored sense; only original connectivity is shown.
        </p>
      )}
      <div className="pm-grid" style={{ gridTemplateColumns: `28px repeat(${k}, minmax(34px, 44px))` }} role="group"
        aria-label={`Entrance pair connectivity, ${title}`}>
        <div aria-hidden />
        {entrances.map((e) => <div key={`h-${e.index}`} className="pm-h" aria-hidden>{e.label}</div>)}
        {entrances.map((ei) => (
          <div key={`r-${ei.index}`} style={{ display: "contents" }}>
            <div className="pm-h" aria-hidden>{ei.label}</div>
            {entrances.map((ej) => {
              const i = Math.min(ei.index, ej.index);
              const j = Math.max(ei.index, ej.index);
              if (ei.index >= ej.index) {
                return <div key={ej.index} className={`pm-cell pm-void${ei.index === ej.index ? " diag" : ""}`} aria-hidden />;
              }
              const st = byPair.get(`${i}-${j}`);
              const orig = linkedOriginal(i, j);
              const change = valid && st ? st.change : "unchanged";
              const final = valid && st ? st.final : orig;
              const isSel = !!selected && selected[0] === i && selected[1] === j;
              const label = `${ei.label}–${ej.label}: originally ${orig ? "linked" : "not linked"}; ${
                change === "unchanged" ? "unchanged" : change} → ${final ? "linked" : "not linked"}`;
              return (
                <button key={ej.index} type="button" aria-pressed={isSel} aria-label={label} title={label}
                  className={`pm-cell pm-${change}${isSel ? " selected" : ""}`}
                  onClick={() => store.set({ selectedPair: isSel ? null : [i, j], t: 0 })}>
                  <span className={`pm-dot${final ? " on" : ""}`} aria-hidden />
                  {CHANGE_ICON[change] && <span className="pm-icon" aria-hidden>{CHANGE_ICON[change]}</span>}
                </button>
              );
            })}
          </div>
        ))}
      </div>
      <div className="legend xsmall">
        <span><span className="pm-dot on inline" aria-hidden /> linked after</span>
        <span><span className="pm-dot inline" aria-hidden /> not linked after</span>
        <span className="lg-opened">↗ opened</span>
        <span className="lg-closed">✕ closed</span>
      </div>
    </div>
  );
}

/* ---- checks, arithmetic -------------------------------------------------------------------- */

export function ChecksList({ checks }: { checks: Check[] }) {
  return (
    <ul className="checks">
      {checks.map((c) => (
        <li key={c.code} className={`check ${c.status}`}>
          <span className="check-icon" aria-hidden>{c.status === "pass" ? "✓" : c.status === "fail" ? "✕" : "–"}</span>
          <div>
            <div className="check-title">
              {CHECK_LABEL[c.code] ?? c.code}
              <span className="sr-only"> — {c.status}</span>
            </div>
            <div className="xsmall dim">{c.message}</div>
            {c.cells.length > 0 && (
              <div className="xsmall faint mono">cells: {c.cells.map((x) => `(${x.join(",")})`).join(" ")}</div>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

export function ScoreArithmetic({ outcome, verified }: { outcome: OutcomeView; verified?: boolean }) {
  if (!outcome.valid) {
    return (
      <div className="arith">
        <div className="arith-line">
          <span className="badge bad">✕ {categoryLabel(outcome.category)}</span>
          <span>Invalid answers score</span>
          <strong className="num">0</strong>
        </div>
        <div className="xsmall faint">Certified optimum v* = {outcome.v_star}. No partial credit for illegal objects.</div>
      </div>
    );
  }
  const v = outcome.raw_objective ?? 0;
  return (
    <div className="arith">
      <div className="arith-line">
        <span className="dim">changed pairs</span>
        <span className="mono">v = {outcome.opened} opened + {outcome.closed} closed = <strong>{v}</strong></span>
      </div>
      <div className="arith-line">
        <span className="dim">certified optimum</span>
        <span className="mono">v* = <strong>{outcome.v_star}</strong>
          {verified !== undefined && (verified ? <span className="badge ok" style={{ marginLeft: 8 }}>✓ independently verified</span>
            : <span className="badge warn" style={{ marginLeft: 8 }}>unverified</span>)}
        </span>
      </div>
      <div className="arith-line">
        <span className="dim">score</span>
        <span className="mono">100 × {v} ÷ {outcome.v_star} = <strong>{outcome.score.toFixed(1)}</strong></span>
      </div>
      <div className="xsmall faint">{outcome.move_count} relocation{outcome.move_count === 1 ? "" : "s"} used. Move count never changes the score.</div>
    </div>
  );
}

/* ---- 2D layers (fallback view and practice editor) -------------------------------------- */

export interface LayersProps {
  state: GridState | null;
  entrances: EntranceInfo[];
  editable: EditableCellInfo[];
  outcome?: OutcomeView | null;
  offending?: Cell[];
  pathCells?: Cell[];
  // practice editor
  onCellClick?: (id: number) => void;
  pendingRemove?: number[];
  pendingAdd?: number[];
  title?: string;
}

export function Layers2D({ state, entrances, editable, outcome, offending, pathCells, onCellClick, pendingRemove,
  pendingAdd, title }: LayersProps) {
  if (!state) return <div className="voxel-placeholder small">No object could be built from this answer.</div>;
  const solid = solidSet(state.occupancy);
  const ent = new Map(entrances.map((e) => [cellKey(e.cell), e.label]));
  const ed = new Map(editable.map((e) => [cellKey(e.cell), e]));
  const removed = new Set((outcome?.removed ?? []).map(cellKey));
  const added = new Set((outcome?.added ?? []).map(cellKey));
  const bad = new Set((offending ?? []).map(cellKey));
  const onPath = new Set((pathCells ?? []).map(cellKey));
  const pr = new Set(pendingRemove ?? []);
  const pa = new Set(pendingAdd ?? []);
  return (
    <div className="layers" role="group" aria-label={title ? `${title}: layers` : "Layers"}>
      {[3, 2, 1, 0].map((z) => (
        <div className="layer" key={z}>
          <div className="xsmall faint">z = {z}{z === 0 ? " (bottom)" : z === 3 ? " (top)" : ""}</div>
          <div className="layer-grid" role="grid" aria-label={`layer z=${z}`}>
            {[0, 1, 2, 3].map((y) =>
              [0, 1, 2, 3].map((x) => {
                const k = `${x},${y},${z}`;
                const e = ed.get(k);
                let cls = solid.has(k) ? "lc solid" : "lc empty";
                if (e) cls += " editable";
                if (removed.has(k)) cls += " removed";
                if (added.has(k)) cls += " added";
                if (bad.has(k)) cls += " offending";
                if (onPath.has(k)) cls += " path";
                if (e && pr.has(e.id)) cls += " pending-remove";
                if (e && pa.has(e.id)) cls += " pending-add";
                const label = ent.get(k) ?? (e ? String(e.id) : "");
                const desc = `(${x},${y},${z}) ${solid.has(k) ? "solid" : "empty"}${ent.has(k) ? `, entrance ${ent.get(k)}` : ""}${
                  e ? `, editable ${e.id}` : ""}${removed.has(k) ? ", removed" : ""}${added.has(k) ? ", added" : ""}`;
                if (onCellClick && e) {
                  return (
                    <button key={k} type="button" className={`${cls} clickable`} aria-label={desc}
                      aria-pressed={pr.has(e.id) || pa.has(e.id)} onClick={() => onCellClick(e.id)}>
                      {label}
                    </button>
                  );
                }
                return <div key={k} className={cls} role="gridcell" aria-label={desc} title={desc}>{label}</div>;
              }),
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
