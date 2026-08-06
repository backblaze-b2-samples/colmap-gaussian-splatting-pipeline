<!-- last_verified: 2026-08-06 -->
# Feature: Captures library + dashboard

## Purpose
Give an at-a-glance view of the app's own reconstructions — a scoped library of
captures plus domain metrics (captures, frames ingested, sparse points, artifact
storage on B2) — distinct from the kept full-bucket File Explorer.

## Used By
- UI: `/` (dashboard) and `/captures` (library)
- API: `GET /captures`, `GET /captures/stats`

## Core Functions
- `apps/web/src/components/dashboard/stats-cards.tsx` — capture + storage stat cards
- `apps/web/src/components/dashboard/recent-captures-table.tsx` — recent captures
- `apps/web/src/components/dashboard/upload-chart.tsx` — B2 write activity, last 7 days
- `apps/web/src/components/captures/captures-list.tsx` — the scoped Captures library
- `services/api/app/service/captures.py` — `get_capture_stats()`, `list_captures()`

## Canonical Files
- Stats service: `services/api/app/service/captures.py`
- Library: `apps/web/src/components/captures/captures-list.tsx`

## Inputs
- None (both screens load automatically via TanStack Query hooks)

## Outputs
- `GET /captures/stats` -> `CaptureStats` (totals by status, images ingested, sparse points, artifact + source bytes)
- `GET /captures` -> `Capture[]` (newest first)

## Flow
- Stats scan the `captures/` prefix and read each manifest; the shared bucket listing cache avoids double scans
- The library and dashboard poll every few seconds while any capture is `running`, so status flips and new previews appear without a manual refresh
- Cards state the wait in words while the first scan runs instead of showing silent placeholders

## Edge Cases
- API unavailable -> inline error state with retry (never a false zero)
- No captures -> empty states on cards, table, and library
- Bucket changed elsewhere -> numbers can lag by up to `LIST_CACHE_TTL_SECONDS`; the app's own writes invalidate the cache

## UX States
- Loading: skeletons + a "Loading capture metrics…" notice
- Empty: "No captures yet" with a New capture CTA
- Loaded: populated cards, chart, table, and capture cards with previews

## Verification
- Test files: `services/api/tests/test_captures.py`, `apps/web/src/components/captures/capture-status-badge.test.ts`
- Focused verify command: `pnpm test:web`
- Default pre-PR verify command: `pnpm verify`
- Pass criteria: stats aggregate across captures; the library renders each status

## Related Docs
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [App Workflows](../app-workflows.md)
