# Implementation tracker (repository mirror)

The Notion database is the live status source. This session had **no Notion access**, so per hub
rule 9 every update below is a *pending* handoff awaiting synchronization to Notion
(see `docs/HUB_SYNC.md`). Timestamps are UTC.

| Prompt | Status | Agent owner | Branch / worktree | Claimed at | Last heartbeat | Reviewer | Next action |
|---|---|---|---|---|---|---|---|
| P1 — Formal engine, exact solver and shared contracts | In review | Claude Code (Opus 5.5), session 6401540c | `p1/formal-engine` → `main` | 2026-09-25T21:40Z | 2026-09-25T22:10Z | self-review only (independent review pending) | Independent reviewer repeats `docs/handoffs/P1.md` commands |
| P2 — Certified packs, compact prompts and research design | In review | Claude Code (Opus 5.5), session 6401540c | `p2/packs` → `main` | 2026-09-25T22:15Z | 2026-09-25T23:05Z | self-review only (independent review pending) | Independent reviewer repeats `docs/handoffs/P2.md` commands |
| P3 — FastAPI, OpenRouter and durable evaluation runner | In review | Claude Code (Opus 5.5), session 6401540c | `p3/backend` → `main` | 2026-09-25T23:10Z | 2026-09-25T23:55Z | self-review only (independent review pending) | Live completion check with a key and cap (P5); independent review |
| P4 — Polished React interface and Three.js comparisons | Ready | — | — | — | — | — | Build comparison view on `contracts/fixtures/replays` |
| P5 — Integration, single-container release and research pilot | Not started | — | — | — | — | — | After P1–P4 |

Status meanings follow the hub: *In review* = reproducible evidence recorded; *Done* additionally
requires review evidence. Self-review is labelled as such and does not count as independent review.
