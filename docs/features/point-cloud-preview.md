<!-- last_verified: 2026-08-06 -->
# Feature: Point-cloud preview

## Purpose
Render a headless preview image of the sparse point cloud so the reconstruction
is visible in the UI without any browser 3D engine — robust, keyless, CPU-only.

## Used By
- UI: capture card thumbnail (`/captures`) and capture detail preview
- API: preview PNG served from B2 via a short-lived presigned URL

## Core Functions
- `app.repo.preview.render_point_cloud` — matplotlib (Agg) 3D scatter to PNG bytes

## Canonical Files
- `services/api/app/repo/preview.py`

## Inputs
- points: Nx3 numpy array (sparse cloud), optional Nx3 colors in [0, 1]

## Outputs
- `captures/<id>/previews/preview.png` on B2; `capture.preview_key`

## Flow
- Force the Agg backend; use the object-oriented `Figure` API (no pyplot global state)
- Subsample above 40k points (deterministic), color by point RGB or by depth
- Equalize axes so the shape isn't distorted; save PNG bytes

## Edge Cases
- Empty cloud or a render failure -> a small "preview unavailable" placeholder PNG (never raises)
- Runs inside the isolated SfM worker process (no thread-unsafe pyplot state)

## UX States
- Placeholder tile when there is no preview yet; skeleton while the image loads

## Verification
- Test files: `services/api/tests/test_sfm_engine.py`
- Focused verify command: `cd services/api && .venv/bin/python -m pytest tests/test_sfm_engine.py -k render`
- Default pre-PR verify command: `pnpm verify`
- Pass criteria: valid PNG bytes for a populated cloud and for an empty cloud

## Related Docs
- [sfm-reconstruction.md](sfm-reconstruction.md)
