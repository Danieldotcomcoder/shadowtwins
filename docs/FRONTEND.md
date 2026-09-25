# Frontend (P4)

React 19 + TypeScript + Vite 8, React Three Fiber 9 / three.js 0.186, TanStack Query, React Router 7,
Radix primitives, cmdk. Served by FastAPI from `frontend/dist` on the same origin as the API.

```
pnpm --dir frontend install
pnpm --dir frontend gen:types     # contracts/openapi.json -> src/api/openapi.d.ts
pnpm --dir frontend build         # tsc -b && vite build
pnpm --dir frontend test          # vitest: fixture cross-checks, contract drift, components
pnpm --dir frontend e2e           # Playwright against a real backend (mock provider, fresh DB)
```

For development run `uv run benchserver dev` (port 8000) and `pnpm --dir frontend dev`
(Vite proxies `/api`).

## Principles

* The browser never decides validity or scores. Every mask, component, route, pair status and
  check it draws comes from the evaluator's replay/evaluation documents. The practice preview only
  shows geometry; the server scores submissions.
* Mock and fixture data are always labelled (`Mock · test double`, "Formal fixture — not a model
  result"); mock runs cannot reach the leaderboard (server-enforced).
* One coordinate mapping: task `(x, y, z)` → scene `(x − 1.5, z − 1.5, y − 1.5)`
  (`src/lib/geometry.ts`). Original / Model / Optimal share one view store (camera, slice,
  transparency, selected pair, route playback), so they stay synchronized.
* Edits inside the object are drawn as x-ray outlines (red removed, teal added, red offending
  cells) and routes/regions render above the geometry, so nothing important is hidden.
* Invalid answers are shown "as requested" with a banner, their failing checks and offending
  cells, and never with pair changes or animated routes.

## Accessibility and fallbacks

Keyboard: every 3D stage is focusable (arrows rotate, +/− zoom, R resets); pair cells are toggle
buttons with full text labels ("A–B: originally linked; closed → not linked"). Non-colour cues:
✓/✕/↗ icons, dashed outlines, hatching and "≠" on changed silhouette pixels, cube vs diamond
region markers. `prefers-reduced-motion` disables route animation and CSS motion. Without WebGL
(or on request) a 2D layer view with the same data replaces the canvases. Narrow screens (≤ 900 px)
use tabs instead of three squeezed views. Rendering is on demand and paused offscreen.

## Verification (reference device)

Playwright Chromium headless shell 153 (SwiftShader WebGL) on Windows 11: desktop 1440×900 and
Pixel 7 emulation. `pnpm --dir frontend e2e` covers the evaluate→run→live-completion flow,
inspection (3 synchronized canvases, 9 silhouette panels, pair selection, keyboard, 2D toggle),
invalid answers, pause/resume, practice submission, reduced motion, no-WebGL fallback,
leaderboard empty state, axe-core scan of 8 pages (no serious/critical violations; colour
contrast excluded from the automated gate), and mobile tabs/no horizontal scroll.
`node frontend/e2e/screenshots.mjs <base> docs/screenshots` refreshes the images in
`docs/screenshots/`.
