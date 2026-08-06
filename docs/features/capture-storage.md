<!-- last_verified: 2026-08-06 -->
# Feature: Versioned artifact store on B2

## Purpose
Make Backblaze B2 the durable, versioned system of record for a capture's whole
lifecycle — raw frames, SfM outputs, staged bundle, previews, and the manifest —
all under the capture's own prefix, with object versions surfaced in the UI.

## Used By
- UI: capture detail Artifacts card (download + version id); Captures library
- API: written during run; read on `GET /captures`, downloaded via presigned URLs

## Core Functions
- `app.repo.artifacts.put_bytes` / `get_bytes` / `list_under` / `delete_under`
- `app.repo.artifacts.head_version_id` / `list_versions` — B2 object versions
- `app.service.captures` — manifest store (`manifest.json` is the source of truth)

## Canonical Files
- `services/api/app/repo/artifacts.py`
- `services/api/app/service/captures.py`

## Inputs
- artifact bytes + content type (from the reconstruction)
- capture id (prefixes every key)

## Outputs
- objects under `captures/<id>/{inputs,sparse,bundle,previews}/` + `manifest.json`
- `CaptureArtifact` entries with `version_id` (when bucket versioning is on)

## Flow
- Every write goes through `repo.artifacts` (boto3 confined to `repo/`)
- On write, capture the current object version id for the Artifacts view
- Listing captures = list `captures/` + read each manifest (no database)
- Delete is scoped to `captures/<id>/` and refuses any non-slash-terminated prefix

## Edge Cases
- Bucket versioning suspended -> `version_id` is null; UI simply omits the version
- Missing manifest -> clean 404; unreadable manifest -> skipped in listings
- Delete never issues a bucket-wide wipe (guarded prefix)

## UX States
- Artifacts card lists each object with size + truncated version id + Download

## Verification
- Test files: `services/api/tests/test_captures.py`
- Focused verify command: `cd services/api && .venv/bin/python -m pytest tests/test_captures.py -k delete`
- Default pre-PR verify command: `pnpm verify`
- Pass criteria: delete is prefix-scoped; unrelated objects survive

## Related Docs
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [docs/SECURITY.md](../SECURITY.md)
