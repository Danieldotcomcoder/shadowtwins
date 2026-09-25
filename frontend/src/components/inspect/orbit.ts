/* Minimal orbit controls on a DOM element that write to the shared view store (pointer drag,
   wheel/pinch zoom, keyboard). Keeping our own controller keeps every view exactly in sync. */

import { useEffect } from "react";
import { clampDist, clampEl, type ViewStore } from "./store";

export function useOrbitControls(el: HTMLElement | null, store: ViewStore) {
  useEffect(() => {
    if (!el) return;
    let dragging = false;
    let lastX = 0;
    let lastY = 0;
    const pointers = new Map<number, { x: number; y: number }>();
    let pinchDist = 0;

    const down = (e: PointerEvent) => {
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 1) {
        dragging = true;
        lastX = e.clientX;
        lastY = e.clientY;
      } else if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinchDist = Math.hypot(a.x - b.x, a.y - b.y);
      }
      el.setPointerCapture(e.pointerId);
    };
    const move = (e: PointerEvent) => {
      if (!pointers.has(e.pointerId)) return;
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinchDist > 0) store.set((s) => ({ dist: clampDist(s.dist * (pinchDist / d)) }));
        pinchDist = d;
        return;
      }
      if (!dragging) return;
      const dx = e.clientX - lastX;
      const dy = e.clientY - lastY;
      lastX = e.clientX;
      lastY = e.clientY;
      store.set((s) => ({ az: s.az - dx * 0.008, el: clampEl(s.el + dy * 0.008) }));
    };
    const up = (e: PointerEvent) => {
      pointers.delete(e.pointerId);
      if (pointers.size === 0) dragging = false;
      if (pointers.size < 2) pinchDist = 0;
    };
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      store.set((s) => ({ dist: clampDist(s.dist * (e.deltaY > 0 ? 1.08 : 1 / 1.08)) }));
    };
    const key = (e: KeyboardEvent) => {
      const step = e.shiftKey ? 0.25 : 0.1;
      switch (e.key) {
        case "ArrowLeft":
          store.set((s) => ({ az: s.az + step }));
          break;
        case "ArrowRight":
          store.set((s) => ({ az: s.az - step }));
          break;
        case "ArrowUp":
          store.set((s) => ({ el: clampEl(s.el + step) }));
          break;
        case "ArrowDown":
          store.set((s) => ({ el: clampEl(s.el - step) }));
          break;
        case "+":
        case "=":
          store.set((s) => ({ dist: clampDist(s.dist / 1.1) }));
          break;
        case "-":
        case "_":
          store.set((s) => ({ dist: clampDist(s.dist * 1.1) }));
          break;
        case "r":
        case "R":
          store.resetCamera();
          break;
        default:
          return;
      }
      e.preventDefault();
    };
    el.addEventListener("pointerdown", down);
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
    el.addEventListener("wheel", wheel, { passive: false });
    el.addEventListener("keydown", key);
    return () => {
      el.removeEventListener("pointerdown", down);
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", up);
      el.removeEventListener("wheel", wheel);
      el.removeEventListener("keydown", key);
    };
  }, [el, store]);
}
