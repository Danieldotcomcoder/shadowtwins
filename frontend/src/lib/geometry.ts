/* Task geometry helpers. Task coordinates: x = column, y = row, z = layer (0 = bottom);
   occupancy character i is cell x + 4y + 16z. Three.js is y-up, so the scene maps
   task (x, y, z) -> scene (x - 1.5, z - 1.5, y - 1.5): layers stack upward and rows run toward
   the default camera. Every view uses this single mapping. */

import type { Cell, GridState, Rows } from "../api/types";

export const N = 4;

export const index = (x: number, y: number, z: number) => x + N * y + N * N * z;

export function coords(i: number): Cell {
  return [i % N, Math.floor(i / N) % N, Math.floor(i / (N * N))];
}

export function toScene([x, y, z]: Cell | number[]): [number, number, number] {
  return [x - 1.5, z - 1.5, y - 1.5];
}

export const cellKey = (c: Cell | number[]) => `${c[0]},${c[1]},${c[2]}`;

export function solidSet(occupancy: string): Set<string> {
  const s = new Set<string>();
  for (let i = 0; i < occupancy.length; i++) if (occupancy[i] === "1") s.add(cellKey(coords(i)));
  return s;
}

export function solidCells(occupancy: string): Cell[] {
  const out: Cell[] = [];
  for (let i = 0; i < occupancy.length; i++) if (occupancy[i] === "1") out.push(coords(i));
  return out;
}

/** Independent re-computation of the three OR projections, used only to cross-check that the
 *  evaluator masks we draw match the occupancy (never to decide validity). */
export function projections(occupancy: string): { x: Rows; y: Rows; z: Rows } {
  const solid = (x: number, y: number, z: number) => occupancy[index(x, y, z)] === "1";
  const grid = () => Array.from({ length: N }, () => Array(N).fill(0) as number[]);
  const x = grid();
  const y = grid();
  const z = grid();
  for (let a = 0; a < N; a++) {
    for (let b = 0; b < N; b++) {
      for (let t = 0; t < N; t++) {
        if (solid(t, a, b)) x[b][a] = 1; // view along x: rows[z][y]
        if (solid(a, t, b)) y[b][a] = 1; // view along y: rows[z][x]
        if (solid(a, b, t)) z[b][a] = 1; // view along z: rows[y][x]
      }
    }
  }
  return { x, y, z };
}

export function adjacent(a: Cell, b: Cell): boolean {
  return Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2]) === 1;
}

/** A path is drawable only if it is a chain of face-adjacent empty cells between its endpoints. */
export function validPath(state: GridState, cells: Cell[], from: Cell, to: Cell): boolean {
  if (cells.length === 0) return false;
  const solid = solidSet(state.occupancy);
  if (cellKey(cells[0]) !== cellKey(from) || cellKey(cells[cells.length - 1]) !== cellKey(to)) return false;
  for (let k = 0; k < cells.length; k++) {
    if (solid.has(cellKey(cells[k]))) return false;
    if (k > 0 && !adjacent(cells[k - 1], cells[k])) return false;
  }
  return true;
}

export function linkedPairs(state: GridState): Set<string> {
  const out = new Set<string>();
  const comp = state.entrance_component;
  for (let i = 0; i < comp.length; i++)
    for (let j = i + 1; j < comp.length; j++) if (comp[i] !== -1 && comp[i] === comp[j]) out.add(`${i}-${j}`);
  return out;
}

export const AXES = {
  x: { title: "View along x", u: "y", v: "z", note: "side" },
  y: { title: "View along y", u: "x", v: "z", note: "front" },
  z: { title: "View along z", u: "x", v: "y", note: "top" },
} as const;
