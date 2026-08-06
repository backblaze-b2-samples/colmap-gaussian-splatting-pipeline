<!-- last_verified: 2026-08-06 -->
# Feature: COLMAP Structure-from-Motion (primary)

## Purpose
Reconstruct a sparse 3D point cloud and camera poses from a Capture's frames by
running real COLMAP structure-from-motion on CPU — the marquee workload and the
lifecycle of the primary entity, **Capture**.

## Used By
- UI: Captures library (`/captures`), capture detail (`/captures/[id]`) — Run / Re-run
- API: `POST /captures/{id}/run`, `GET /captures/{id}` (poll status/stages)
- Job: background daemon thread -> isolated `spawn` worker process

## Core Functions
- `app.repo.sfm.run_sfm` — SIFT extraction (CPU) -> matching -> incremental mapping
- `app.repo.sfm.detect_device` — CUDA -> else CPU auto-detect (MPS N/A to COLMAP)
- `app.service.sfm_runner.run_sfm_isolated` — runs the engine in a separate process
- `app.service.capture_runner.run_capture` / `_execute` — lifecycle + artifact writes

## Canonical Files
- Engine: `services/api/app/repo/sfm.py`
- Isolation: `services/api/app/service/sfm_runner.py`
- Orchestration: `services/api/app/service/capture_runner.py`

## Inputs
- frames: list[(name, jpeg_bytes)] (downloaded from `captures/<id>/inputs/`)
- quality: low | medium | high (SIFT max features)
- matcher: exhaustive | sequential
- device: cuda | cpu (auto-detected)

## Outputs
- sparse `points.ply`, COLMAP text model (`cameras.txt`, `images.txt`), preview PNG
- `CaptureMetrics` (registered images, sparse points, observations, mean reproj. error, device)
- side effects: writes artifacts under `captures/<id>/`, flips manifest `running -> done|failed`

## Flow
- Stage frames into a temp image dir in the worker process
- `pycolmap.extract_features` (camera model OPENCV, SIFT forced to CPU)
- `pycolmap.match_exhaustive` or `match_sequential`
- `pycolmap.incremental_mapping` -> pick the reconstruction with the most registered images
- Export PLY + text model, build the bundle, render the preview, gate dense MVS on CUDA

## Edge Cases
- < 3 frames -> ValueError ("need at least 3 overlapping views")
- No model registered -> capture marked `failed` with a clear message
- Native COLMAP crash / hang -> isolated child killed; capture `failed`, API unaffected
- No CUDA -> dense MVS stage recorded as `skipped`, bundle staged for GPU training

## UX States
- Empty: no captures yet
- Loading: `running` shows an indeterminate stage list (no fabricated percentage)
- Error: failed captures show the recorded error in an Alert

## Verification
- Test files: `services/api/tests/test_sfm_engine.py`, `tests/test_captures.py`
- Required cases: transforms builder, preview render, device default, run guard, lifecycle
- Focused verify command: `cd services/api && .venv/bin/python -m pytest tests/test_sfm_engine.py tests/test_captures.py`
- Default pre-PR verify command: `pnpm verify`
- Pass criteria: heavy COLMAP tests skip cleanly when `pycolmap` is absent; the rest pass

## Related Docs
- [README.md](../../README.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [splat-staging.md](splat-staging.md)
