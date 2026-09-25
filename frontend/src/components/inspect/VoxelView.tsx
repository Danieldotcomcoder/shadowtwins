import { Edges, Line } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { Cell, EditableCellInfo, EntranceInfo, GridState, OutcomeView } from "../../api/types";
import { cellKey, solidCells, toScene } from "../../lib/geometry";
import { useOrbitControls } from "./orbit";
import { type ViewStore, ViewStoreContext, useView, useViewStore } from "./store";

const COLORS = {
  solid: "#aab3c1",
  editable: "#c9d6ea",
  added: "#7dd3c0",
  offending: "#f27a7a",
  removed: "#f27a7a",
  edge: "#0b0d10",
  entrance: "#e8ebf1",
  path: "#7dd3c0",
  regionA: "#86a8ff",
  regionB: "#f2b54c",
};

export interface VoxelViewProps {
  title: string;
  state: GridState | null;
  outcome?: OutcomeView | null;
  entrances: EntranceInfo[];
  editable: EditableCellInfo[];
  offending?: Cell[];
  invalid?: boolean;
  placeholder?: string;
  store: ViewStore;
  active: boolean;
  badge?: React.ReactNode;
}

const box = new THREE.BoxGeometry(0.94, 0.94, 0.94);
const ghostBox = new THREE.BoxGeometry(0.98, 0.98, 0.98);
const regionBox = new THREE.BoxGeometry(0.34, 0.34, 0.34);
const sphere = new THREE.SphereGeometry(0.15, 20, 14);
const particle = new THREE.SphereGeometry(0.085, 12, 10);
const xrayEdges = new THREE.EdgesGeometry(new THREE.BoxGeometry(1.0, 1.0, 1.0));

type LabelStyle = "entrance" | "entrance-on" | "id" | "axis";
const LABEL_STYLES: Record<LabelStyle, { bg: string | null; fg: string; border: string | null; px: number; scale: number }> = {
  entrance: { bg: "#0b0d10", fg: "#e8ebf1", border: "#3a4250", px: 44, scale: 0.42 },
  "entrance-on": { bg: "#0b0d10", fg: "#7dd3c0", border: "#7dd3c0", px: 44, scale: 0.42 },
  id: { bg: "rgba(233,237,243,0.9)", fg: "#0b0d10", border: null, px: 38, scale: 0.3 },
  axis: { bg: null, fg: "#7f8898", border: null, px: 40, scale: 0.34 },
};
const textureCache = new Map<string, THREE.CanvasTexture>();

function labelTexture(text: string, style: LabelStyle): THREE.CanvasTexture {
  const key = `${style}:${text}`;
  const hit = textureCache.get(key);
  if (hit) return hit;
  const st = LABEL_STYLES[style];
  const canvas = document.createElement("canvas");
  const h = 64;
  const w = Math.max(64, 26 * text.length + 30);
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    if (st.bg) {
      ctx.fillStyle = st.bg;
      ctx.beginPath();
      ctx.roundRect(4, 6, w - 8, h - 12, 10);
      ctx.fill();
      if (st.border) {
        ctx.strokeStyle = st.border;
        ctx.lineWidth = 3;
        ctx.stroke();
      }
    }
    ctx.fillStyle = st.fg;
    ctx.font = `700 ${st.px}px "Inter Variable", system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, w / 2, h / 2 + 2);
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  textureCache.set(key, tex);
  return tex;
}

/** A camera-facing text label drawn above the geometry (sprites, not DOM overlays). */
function Label({ text, position, style, offset = [0, 0, 0] }: {
  text: string; position: [number, number, number]; style: LabelStyle; offset?: [number, number, number];
}) {
  const tex = labelTexture(text, style);
  const img = tex.image as HTMLCanvasElement;
  const scale = LABEL_STYLES[style].scale;
  return (
    <sprite position={[position[0] + offset[0], position[1] + offset[1], position[2] + offset[2]]}
      scale={[scale * (img.width / img.height), scale, 1]} renderOrder={20}>
      <spriteMaterial map={tex} depthTest={false} transparent />
    </sprite>
  );
}

/** Outline drawn on top of everything, so edits inside the object stay visible. */
function XRay({ cell, color }: { cell: Cell; color: string }) {
  return (
    <lineSegments geometry={xrayEdges} position={toScene(cell)} renderOrder={10}>
      <lineBasicMaterial color={color} depthTest={false} transparent opacity={0.95} />
    </lineSegments>
  );
}

function CameraRig() {
  const store = useViewStore();
  const { camera, invalidate } = useThree();
  useEffect(() => {
    const apply = () => {
      const { az, el, dist } = store.get();
      camera.position.set(dist * Math.cos(el) * Math.sin(az), dist * Math.sin(el), dist * Math.cos(el) * Math.cos(az));
      camera.lookAt(0, -0.35, 0);
      invalidate();
    };
    apply();
    return store.subscribe(apply);
  }, [store, camera, invalidate]);
  return null;
}

function Ground() {
  const axisLabel = (text: string, pos: [number, number, number]) => <Label text={text} position={pos} style="axis" />;
  return (
    <group>
      <gridHelper args={[4, 4, "#39414d", "#262c35"]} position={[0, -2.02, 0]} />
      <Line points={[[-2.25, -2.02, -2.25], [2.6, -2.02, -2.25]]} color="#6c7486" lineWidth={1} />
      <Line points={[[-2.25, -2.02, -2.25], [-2.25, -2.02, 2.6]]} color="#6c7486" lineWidth={1} />
      <Line points={[[-2.25, -2.02, -2.25], [-2.25, 2.6, -2.25]]} color="#6c7486" lineWidth={1} />
      {axisLabel("x", [2.85, -2.02, -2.25])}
      {axisLabel("y", [-2.25, -2.02, 2.85])}
      {axisLabel("z", [-2.25, 2.85, -2.25])}
    </group>
  );
}

function PathParticles({ points, active }: { points: THREE.Vector3[]; active: boolean }) {
  const store = useViewStore();
  const { invalidate } = useThree();
  const refs = useRef<(THREE.Mesh | null)[]>([]);
  const count = Math.min(6, Math.max(2, points.length));
  const lengths = useMemo(() => {
    const acc = [0];
    for (let k = 1; k < points.length; k++) acc.push(acc[k - 1] + points[k].distanceTo(points[k - 1]));
    return acc;
  }, [points]);
  useEffect(() => {
    const place = () => {
      const total = lengths[lengths.length - 1] || 1;
      const { t } = store.get();
      for (let k = 0; k < count; k++) {
        const m = refs.current[k];
        if (!m) continue;
        const d = (((t + k / count) % 1) + 1) % 1 * total;
        let seg = 1;
        while (seg < lengths.length - 1 && lengths[seg] < d) seg++;
        const a = points[seg - 1];
        const b = points[Math.min(seg, points.length - 1)];
        const span = lengths[seg] - lengths[seg - 1] || 1;
        m.position.lerpVectors(a, b, Math.min(1, Math.max(0, (d - lengths[seg - 1]) / span)));
      }
      if (active) invalidate();
    };
    place();
    return store.subscribe(place);
  }, [store, points, lengths, count, active, invalidate]);
  return (
    <group>
      {Array.from({ length: count }, (_, k) => (
        <mesh key={k} ref={(m) => { refs.current[k] = m; }} geometry={particle} renderOrder={13}>
          <meshBasicMaterial color="#e9fffa" depthTest={false} />
        </mesh>
      ))}
    </group>
  );
}

function Scene(props: VoxelViewProps) {
  const { state, outcome, entrances, editable, offending, active } = props;
  const maxLayer = useView((s) => s.maxLayer);
  const transparent = useView((s) => s.transparent);
  const showLabels = useView((s) => s.labels);
  const tintEditable = useView((s) => s.editable);
  const pair = useView((s) => s.selectedPair);

  const editableKeys = useMemo(() => new Set(editable.map((e) => cellKey(e.cell))), [editable]);
  const addedKeys = useMemo(() => new Set((outcome?.added ?? []).map(cellKey)), [outcome]);
  const offendingKeys = useMemo(() => new Set((offending ?? []).map(cellKey)), [offending]);
  const solids = useMemo(() => (state ? solidCells(state.occupancy) : []), [state]);
  const visible = (c: Cell | number[]) => c[2] <= maxLayer;

  const pairView = useMemo(() => {
    if (!state || !pair) return null;
    const [i, j] = pair;
    const ci = state.entrance_component[i];
    const cj = state.entrance_component[j];
    if (ci !== -1 && ci === cj) {
      const trace = state.paths.find((p) => p.i === i && p.j === j);
      if (trace) return { kind: "path" as const, points: trace.cells.map((c) => new THREE.Vector3(...toScene(c))) };
    }
    const region = (k: number) => state.empty_components.find((c) => c.entrances.includes(k))?.cells ?? [];
    return { kind: "blocked" as const, a: region(i), b: region(j) };
  }, [state, pair]);

  return (
    <>
      <CameraRig />
      <ambientLight intensity={0.55} />
      <hemisphereLight args={["#dfe8ff", "#20242b", 0.45]} />
      <directionalLight position={[5, 9, 7]} intensity={1.15} />
      <directionalLight position={[-6, 3, -5]} intensity={0.35} />
      <Ground />
      {solids.filter(visible).map((c) => {
        const k = cellKey(c);
        const color = offendingKeys.has(k) ? COLORS.offending : addedKeys.has(k) ? COLORS.added
          : tintEditable && editableKeys.has(k) ? COLORS.editable : COLORS.solid;
        return (
          <mesh key={k} geometry={box} position={toScene(c)}>
            <meshStandardMaterial color={color} roughness={0.62} metalness={0.05}
              transparent={transparent} opacity={transparent ? 0.22 : 1} depthWrite={!transparent} />
            <Edges color={COLORS.edge} threshold={15} />
          </mesh>
        );
      })}
      {(outcome?.removed ?? []).filter(visible).map((c) => (
        <mesh key={`rm-${cellKey(c)}`} geometry={ghostBox} position={toScene(c)}>
          <meshBasicMaterial color={COLORS.removed} transparent opacity={0.08} depthWrite={false} />
          <Edges color={COLORS.removed} threshold={15} />
        </mesh>
      ))}
      {(outcome?.removed ?? []).filter(visible).map((c) => <XRay key={`xr-${cellKey(c)}`} cell={c} color={COLORS.removed} />)}
      {(outcome?.added ?? []).filter(visible).map((c) => <XRay key={`xa-${cellKey(c)}`} cell={c} color={COLORS.added} />)}
      {(offending ?? []).filter(visible).map((c) => <XRay key={`xo-${cellKey(c)}`} cell={c} color={COLORS.offending} />)}
      {entrances.map((e) => {
        const inPair = pair && (pair[0] === e.index || pair[1] === e.index);
        return (
          <group key={`ent-${e.index}`} position={toScene(e.cell)}>
            <mesh geometry={sphere} renderOrder={14}>
              <meshBasicMaterial color={inPair ? COLORS.path : COLORS.entrance} depthTest={false} />
            </mesh>
            <Label text={e.label} position={[0, 0, 0]} style={inPair ? "entrance-on" : "entrance"} offset={[0.22, 0.26, 0]} />
          </group>
        );
      })}
      {showLabels && editable.filter((e) => visible(e.cell)).map((e) => (
        <Label key={`id-${e.id}`} text={String(e.id)} position={toScene(e.cell)} style="id" />
      ))}
      {pairView?.kind === "path" && (
        <>
          <Line points={pairView.points} color={COLORS.path} lineWidth={3} depthTest={false} renderOrder={12} />
          <PathParticles points={pairView.points} active={active} />
        </>
      )}
      {pairView?.kind === "blocked" && (
        <>
          {pairView.a.map((c) => (
            <mesh key={`ra-${cellKey(c)}`} geometry={regionBox} position={toScene(c)}>
              <meshBasicMaterial color={COLORS.regionA} transparent opacity={0.85} depthTest={false} />
            </mesh>
          ))}
          {pairView.b.map((c) => (
            <mesh key={`rb-${cellKey(c)}`} geometry={regionBox} position={toScene(c)} rotation={[0.785, 0.785, 0]}>
              <meshBasicMaterial color={COLORS.regionB} transparent opacity={0.85} depthTest={false} />
            </mesh>
          ))}
        </>
      )}
    </>
  );
}

export function VoxelView(props: VoxelViewProps) {
  const [el, setEl] = useState<HTMLDivElement | null>(null);
  const store = useViewStore();
  useOrbitControls(el, store);
  const { title, state, placeholder, invalid, badge } = props;
  return (
    <div className="voxel-view">
      <div className="voxel-view-head">
        <h3>{title}</h3>
        {badge}
      </div>
      <div
        ref={setEl}
        className={`voxel-stage${invalid ? " invalid" : ""}`}
        tabIndex={0}
        role="img"
        aria-label={`${title}: 3D view. Drag or use arrow keys to rotate, plus and minus to zoom, R to reset. All views share one camera.`}
      >
        {state ? (
          <Canvas frameloop="demand" dpr={[1, 2]} camera={{ fov: 34, near: 0.1, far: 100 }} gl={{ antialias: true }}>
            <ViewStoreContext.Provider value={store}>
              <Scene {...props} />
            </ViewStoreContext.Provider>
          </Canvas>
        ) : (
          <div className="voxel-placeholder">{placeholder ?? "No object"}</div>
        )}
        {invalid && state && (
          <div className="voxel-invalid" role="note">
            <span aria-hidden>✕</span> Invalid answer — shown as requested, not a legal result
          </div>
        )}
      </div>
    </div>
  );
}
