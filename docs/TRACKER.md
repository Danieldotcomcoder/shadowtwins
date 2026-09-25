# Implementation tracker (repository mirror)

The Notion database is the live status source. This session had **no Notion access**, so per hub
rule 9 every update below is a *pending* handoff awaiting synchronization to Notion
(see `docs/HUB_SYNC.md`). Timestamps are UTC.

| Prompt | Status | Agent owner | Branch / worktree | Claimed at | Last heartbeat | Reviewer | Next action |
|---|---|---|---|---|---|---|---|
| P1 — Formal engine, exact solver and shared contracts | In review | Claude Code (Opus 5.5), session 6401540c | `p1/formal-engine` → `main` | 2026-09-25T21:40Z | 2026-09-25T22:10Z | self-review only (independent review pending) | Independent reviewer repeats `docs/handoffs/P1.md` commands |
| P2 — Certified packs, compact prompts and research design | Ready | — | — | — | — | — | Generate development pool; measure shadow activity |
| P3 — FastAPI, OpenRouter and durable evaluation runner | Ready | — | — | — | — | — | Mock-provider vertical slice, then durable execution |
| P4 — Polished React interface and Three.js comparisons | Not started | — | — | — | — | — | Build comparison view on `contracts/fixtures/replays` |
| P5 — Integration, single-container release and research pilot | Not started | — | — | — | — | — | After P1–P4 |

Status meanings follow the hub: *In review* = reproducible evidence recorded; *Done* additionally
requires review evidence. Self-review is labelled as such and does not count as independent review.
