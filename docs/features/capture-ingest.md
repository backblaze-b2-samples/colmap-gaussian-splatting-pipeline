<!-- last_verified: 2026-08-06 -->
# Feature: Capture ingest

## Purpose
Bring a capture's source frames into B2 — from an uploaded image set or by
sampling a capture video server-side — so COLMAP has well-spread, overlapping
views to reconstruct.

## Used By
- UI: capture detail (`/captures/[id]`) — the ingest panel
- API: `POST /captures/{id}/images` (multipart list), `POST /captures/{id}/video` (multipart file)

## Core Functions
- `app.repo.frames.resize_image` — downscale to `max_image_dimension`, re-encode JPEG (PIL, lazy)
- `app.repo.frames.sample_video_frames` — even frame sampling via imageio + bundled ffmpeg (lazy)
- `app.service.captures.ingest_images` / `ingest_video`

## Canonical Files
- `services/api/app/repo/frames.py`
- `services/api/app/service/captures.py`

## Inputs
- images: one or more image files, or video: a single clip (mp4/mov/...)
- max_image_dimension: int (from the capture params)

## Outputs
- JPEG frames written to `captures/<id>/inputs/`
- manifest `input_count` updated; status advances `draft -> ready`

## Flow
- Read uploads with chunked streaming + size cap (`MAX_FILE_SIZE`)
- Images: downscale each, store as `<stem>.jpg`
- Video: sample `VIDEO_FRAME_COUNT` frames evenly (bundled ffmpeg), downscale, store as `frame_NNNN.jpg`
- Recount inputs and persist the manifest

## Edge Cases
- Unreadable image / video -> 400 with a clear message
- Ingest while `running` -> 409 conflict
- No frames decoded from a video -> ValueError surfaced as 400

## UX States
- Empty: draft capture prompts for frames
- Loading: upload button shows a spinner while frames stream + process
- Error: toast with the API message

## Verification
- Test files: `services/api/tests/test_captures.py`
- Focused verify command: `cd services/api && .venv/bin/python -m pytest tests/test_captures.py -k ingest`
- Default pre-PR verify command: `pnpm verify`
- Pass criteria: image ingest advances the capture to `ready` and stores JPEGs under `inputs/`

## Related Docs
- [sfm-reconstruction.md](sfm-reconstruction.md)
- [capture-storage.md](capture-storage.md)
