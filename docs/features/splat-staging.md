<!-- last_verified: 2026-08-06 -->
# Feature: Splat / NeRF staging

## Purpose
Turn a COLMAP reconstruction into a self-contained Nerfstudio/gsplat-ready
bundle on B2, plus the exact command to train a 3D Gaussian Splat on a GPU host
— honestly staging the GPU-only tail rather than faking a trained splat.

## Used By
- UI: capture detail — "Gaussian Splatting / NeRF training" card + Artifacts
- API: produced during `POST /captures/{id}/run`; downloaded via presigned URLs

## Core Functions
- `app.repo.bundle.build_transforms` — Nerfstudio `transforms.json` (OPENCV intrinsics + per-frame camera-to-world)
- `app.repo.bundle.train_command` — the `ns-train splatfacto` command for the staged bundle
- `app.service.capture_runner._write_artifacts` — writes bundle + model to B2

## Canonical Files
- `services/api/app/repo/bundle.py`
- `services/api/app/service/capture_runner.py`

## Inputs
- a COLMAP `Reconstruction` (cameras, images, points3D)
- the registered frames (copied into the bundle)

## Outputs
- `captures/<id>/bundle/transforms.json`, `captures/<id>/bundle/images/<frame>.jpg`
- `captures/<id>/sparse/points.ply`, `cameras.txt`, `images.txt`
- `capture.train_command` — e.g. `ns-train splatfacto --data ./bundle ...`

## Flow
- Convert COLMAP world-to-camera (OpenCV) poses to Nerfstudio camera-to-world (OpenGL axis flip)
- Emit OPENCV intrinsics with distortion coefficients (k1,k2,p1,p2)
- Stage the referenced frames so the bundle is self-contained
- Gate dense MVS on CUDA; on CPU record `dense` skipped and emit the train command

## Edge Cases
- Older `pycolmap` without `cam_from_world.matrix()` -> qvec/tvec fallback
- CUDA host -> dense stage runs; CPU host -> bundle staged + command emitted

## UX States
- Shown only for `done` captures; the card explains whether dense ran or was staged

## Verification
- Test files: `services/api/tests/test_sfm_engine.py`
- Focused verify command: `cd services/api && .venv/bin/python -m pytest tests/test_sfm_engine.py -k "transforms or train"`
- Default pre-PR verify command: `pnpm verify`
- Pass criteria: `transforms.json` carries OPENCV intrinsics + 4x4 frames; command references the bundle

## Related Docs
- [sfm-reconstruction.md](sfm-reconstruction.md)
- [capture-storage.md](capture-storage.md)
