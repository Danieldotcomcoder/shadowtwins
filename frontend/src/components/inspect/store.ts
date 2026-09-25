/* One store per comparison: every view reads the same camera, slice, selection and playback
   state, so Original / Model / Optimal always stay synchronized. */

import { createContext, useContext, useSyncExternalStore } from "react";

export interface ViewState {
  az: number; // azimuth (radians)
  el: number; // elevation (radians)
  dist: number;
  maxLayer: number; // show layers z <= maxLayer (0..3)
  transparent: boolean;
  labels: boolean; // editable-cell ID labels
  editable: boolean; // tint editable cells
  selectedPair: [number, number] | null;
  playing: boolean;
  t: number; // path animation phase 0..1
  speed: number;
}

export const DEFAULT_VIEW: ViewState = {
  az: -0.72,
  el: 0.52,
  dist: 12.5,
  maxLayer: 3,
  transparent: false,
  labels: false,
  editable: true,
  selectedPair: null,
  playing: false,
  t: 0,
  speed: 1,
};

export interface ViewStore {
  get: () => ViewState;
  set: (patch: Partial<ViewState> | ((s: ViewState) => Partial<ViewState>)) => void;
  subscribe: (cb: () => void) => () => void;
  resetCamera: () => void;
}

export function createViewStore(initial: Partial<ViewState> = {}): ViewStore {
  let state: ViewState = { ...DEFAULT_VIEW, ...initial };
  const subs = new Set<() => void>();
  return {
    get: () => state,
    set: (patch) => {
      const p = typeof patch === "function" ? patch(state) : patch;
      state = { ...state, ...p };
      for (const cb of subs) cb();
    },
    subscribe: (cb) => {
      subs.add(cb);
      return () => subs.delete(cb);
    },
    resetCamera: () => {
      state = { ...state, az: DEFAULT_VIEW.az, el: DEFAULT_VIEW.el, dist: DEFAULT_VIEW.dist };
      for (const cb of subs) cb();
    },
  };
}

export const ViewStoreContext = createContext<ViewStore | null>(null);

export function useViewStore(): ViewStore {
  const s = useContext(ViewStoreContext);
  if (!s) throw new Error("ViewStoreContext missing");
  return s;
}

export function useView<T>(select: (s: ViewState) => T): T {
  const store = useViewStore();
  return useSyncExternalStore(store.subscribe, () => select(store.get()), () => select(store.get()));
}

export const clampEl = (el: number) => Math.max(-1.35, Math.min(1.35, el));
export const clampDist = (d: number) => Math.max(5.5, Math.min(22, d));
