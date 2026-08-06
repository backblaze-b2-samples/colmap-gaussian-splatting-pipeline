<!-- last_verified: 2026-08-06 -->
# Architecture

COLMAP Gaussian Splatting Pipeline is a capture-to-B2 photogrammetry app. The
primary entity is a **Capture** — a COLMAP structure-from-motion reconstruction
job whose system of record is a JSON manifest in B2. The starter's UI kit,
full-bucket File Explorer, and Upload are kept; the reconstruction engine,
Captures screens, and photogrammetry dashboard are added.

## Components

- **apps/web/** — Next.js 16 frontend (App Router, Tailwind v4, shadcn/ui)
  - Photogrammetry dashboard (captures, frames ingested, sparse points, artifacts on B2)
  - Captures library + capture detail (ingest, stage timeline, sparse-cloud preview, artifacts, run/edit/delete/re-run)
  - Kept starter surfaces: full-bucket File Explorer, drag-and-drop Upload, Design System
  - Dark mode via `next-themes`
- **services/api/** — FastAPI backend (layered architecture)
  - Capture lifecycle REST API (create/read/update/delete/ingest/run) + kept file/upload endpoints
  - COLMAP structure-from-motion via `pycolmap` (CPU), run in an isolated worker process
  - Nerfstudio/gsplat bundle staging (`transforms.json`, sparse model, `points.ply`) + `ns-train` command
  - Headless matplotlib point-cloud preview render
  - B2 S3 integration via boto3; capture manifests + artifacts stored on B2 (no database)
  - Health check, structured JSON logging with request tracing, Prometheus-format metrics
- **packages/shared/** — TypeScript type definitions
  - Mirrors Pydantic models from the API (incl. `Capture`, `CaptureStats`)
  - Consumed by `apps/web/` as workspace dependency

## Reconstruction pipeline

The heavy compute is confined to `repo/` with LAZY imports (the wheels are never
needed to import the app, collect tests, or export the OpenAPI contract):

```
repo/frames.py    Video frame sampling (imageio + bundled ffmpeg) + image downscale (PIL)
repo/sfm.py       COLMAP SfM engine (pycolmap): SIFT (CPU) -> match -> incremental mapping
repo/bundle.py    Nerfstudio transforms.json builder, sparse point extraction, ns-train command
repo/preview.py   Headless matplotlib sparse point-cloud render (Agg backend)
repo/artifacts.py B2 manifest + artifact I/O (boto3): put/get/list/delete + object versions
```

Orchestration lives in `service/`: `service/captures.py` owns the lifecycle and
the B2-backed manifest store; `service/capture_runner.py` runs a capture and
persists artifacts; `service/sfm_runner.py` executes `repo.sfm.run_sfm` in an
isolated `spawn` process so a native COLMAP crash/segfault or a hang is contained
to that child and turned into a `failed` manifest — it can never wedge the API.

**Device gating.** `repo.sfm.detect_device()` auto-detects the compute device:
CUDA if a CUDA-capable `pycolmap`/`nvidia-smi` is present, else CPU (MPS is N/A
to COLMAP's C++/CUDA kernels). Sparse SfM always runs on CPU. Dense MVS and
gsplat/NeRF training are CUDA-only: on a CPU host the pipeline stages the bundle
and emits the exact `ns-train` command instead of faking a trained splat. No GPU
is ever hard-required.

## Backend Layering

The API follows a strict layered architecture:

```
types/     Pydantic models — no logic, no imports from other layers
  |
config/    Settings (pydantic-settings) — depends only on types
  |
repo/      Data access (boto3 B2 client) — no business logic
  |
service/   Business logic — calls repo, returns types
  |
runtime/   FastAPI routes — calls service, never repo directly
```

### Layering Rules

1. Dependencies flow downward only: `types` -> `config` -> `repo` -> `service` -> `runtime`
2. No backward imports (e.g., service must not import from runtime)
3. `boto3` only allowed in `repo/` layer
4. All boundary data uses Pydantic models (no raw dicts across layers)
5. Each file stays under 300 lines

### Directory Structure

```
services/api/
  main.py                  App entrypoint, middleware, router registration
  app/
    types/                 Pydantic models (Capture, CaptureStats, FileMetadata, ...)
    config/                Settings loaded from environment
    repo/                  B2 S3 client + reconstruction engine (sfm/bundle/preview/frames/artifacts)
    service/               Lifecycle + run orchestration (captures, capture_runner, sfm_runner)
    runtime/               FastAPI route handlers (captures, files, upload, ...)
  scripts/                 export_openapi.py, seed_demo.py (optional synthetic capture)
  tests/                   pytest tests (structural + integration + engine units)
```

## Boundary Invariants

- **No external SDK leakage**: `boto3` is only imported in `app/repo/`. All other layers interact with B2 through the repo interface.
- **No raw dicts at boundaries**: All data crossing layer boundaries uses typed Pydantic models.
- **No cross-layer mutable state**: Configuration is read-only after init, and no mutable state is shared *between* layers. Intra-layer caches/counters (the listing cache in `repo/list_cache.py`, the B2 connectivity cache in `repo/b2_client.py`, the download counter in `repo/counter.py`, the rate-limit and metrics state in `runtime/`) are module-local and guarded by a `threading.Lock`. The listing cache also owns the only background thread in the app: a stale entry is served immediately while that thread re-scans (stale-while-revalidate), and `main.lifespan` warms it once at startup so no user pays for the cold full-bucket scan.
- **Validated inputs**: All HTTP inputs validated by FastAPI/Pydantic. File keys reject empty and path-traversal patterns; optional prefix confinement via `ALLOWED_KEY_PREFIX` (off by default).

## Deployment

- **Local dev** — `pnpm dev` runs both services via `concurrently`
  - Web: `localhost:3000`
  - API: `localhost:8000`
- **Railway** — two services from the same repository: `web` builds from the
  repository root because it consumes `packages/shared`; `api` builds from
  `services/api`. The versioned per-service configs and the human-approved
  staging/production contract live in [infra/railway/README.md](infra/railway/README.md).
- **Vercel** — one project using [Vercel Services](https://vercel.com/docs/services):
  the `web` (Next.js) and `api` (FastAPI) services build from the same repo and
  share one origin — the web app at `/`, the API under `/api`. The repo-root
  `vercel.json` declares both services and routes `/api/*` to the API service;
  the Vercel-only `services/api/index.py` strips the `/api` prefix so FastAPI
  keeps its native paths (`/health`, `/files`, …). It is suitable only for
  uploads below Vercel's 4.5 MB Function payload ceiling. A
  two-separate-Projects alternative and the full delivery contract live in
  [infra/vercel/README.md](infra/vercel/README.md).

External provisioning and deployment remain explicit user-approved actions.

## Data Stores

- **Backblaze B2** — object storage (S3-compatible API), the sole data store
  - Each capture is a B2 prefix `captures/<id>/` holding `manifest.json`
    (status, params, stages, metrics, artifacts, timestamps), `inputs/` (raw
    frames), `sparse/` (COLMAP model + `points.ply`), `bundle/`
    (`transforms.json` + registered frames), and `previews/` (preview PNG)
  - Listing captures = list `captures/` + read each manifest; **no database**
  - Object versions surfaced per artifact via `list_object_versions`
    (degrades gracefully when bucket versioning is suspended)
  - `delete` is strictly prefix-scoped to `captures/<id>/` — never bucket-wide

## External Services

- **Backblaze B2 S3 API** — file storage, retrieval, deletion, presigned URLs

## Trust Boundaries

See [docs/SECURITY.md](docs/SECURITY.md) for full security documentation.

- **Frontend -> API** — CORS-restricted to configured origins. `CORSMiddleware` is registered LAST in `main.py` (outermost) so it wraps **every** response, including uncaught-exception 500s — otherwise the browser would block error responses and the UI would only see an opaque "network error". See [docs/RELIABILITY.md](docs/RELIABILITY.md#error-handling). A per-IP rate-limit middleware sits inner to CORS; see [docs/SECURITY.md](docs/SECURITY.md#rate-limiting).
- **API -> B2** — authenticated via application keys, signature v4
- **Client -> B2** — presigned URLs for download (10-min expiry, forced attachment)

## Data Flows

- **Create capture**: Browser -> `POST /captures` -> service writes a `draft` manifest to B2
- **Ingest**: Browser -> `POST /captures/{id}/images` or `/video` (multipart) -> repo.frames downscales/samples -> repo.artifacts writes frames to `inputs/` -> manifest `ready`
- **Run**: Browser -> `POST /captures/{id}/run` -> manifest `running` -> background thread downloads frames -> `sfm_runner` runs COLMAP in an isolated process -> capture_runner writes sparse model + bundle + preview to B2 -> manifest `done`/`failed`. The frontend polls the manifest while `running`.
- **Read**: Browser -> `GET /captures` / `GET /captures/{id}` -> service reads manifests from B2
- **Download artifact**: Browser -> `GET /files-by-key/download` -> repo generates a presigned URL -> browser downloads
- **Delete**: Browser -> `DELETE /captures/{id}` -> service deletes the capture's own prefix from B2 (scoped)

## Observability

- Structured JSON logging on all requests with `request_id`
- Request timing middleware (logs duration per request; also the catch-all that converts uncaught exceptions to a typed JSON 500)
- `/metrics` endpoint (Prometheus format: request count, latency, upload count)
- `/health` endpoint (B2 connectivity check)

## API Contract

- Checked-in OpenAPI artifact: `docs/api/openapi.json`
- Export/check command: `pnpm contract:export` / `pnpm contract:check`
- FastAPI freshness test: `services/api/tests/test_openapi_contract.py`
- Frontend route drift test: `apps/web/src/lib/api-contract.test.ts`

The frontend client keeps a small `API_CLIENT_ROUTES` registry in
`apps/web/src/lib/api-client.ts`. Tests compare that registry to the checked-in
OpenAPI artifact so route changes fail loudly before the hand-written client can
silently drift from FastAPI. `GET /metrics` is intentionally server-only.

## Canonical Files

- Capture routes: `services/api/app/runtime/captures.py`
- Capture lifecycle + manifest store: `services/api/app/service/captures.py`
- Run orchestration: `services/api/app/service/capture_runner.py`
- Isolated worker: `services/api/app/service/sfm_runner.py`
- COLMAP engine (repo): `services/api/app/repo/sfm.py` (+ `bundle.py`, `preview.py`, `frames.py`)
- B2 manifest/artifact I/O (repo): `services/api/app/repo/artifacts.py`; base client: `repo/b2_client.py`
- Pydantic models: `services/api/app/types/` (`captures.py`, `files.py`, `upload.py`, `stats.py`, `formatting.py`)
- Config (pydantic-settings): `services/api/app/config/settings.py`
- Structural tests: `services/api/tests/test_structure.py`; engine units: `tests/test_sfm_engine.py`; lifecycle: `tests/test_captures.py`
- OpenAPI contract: `docs/api/openapi.json`; exporter: `services/api/scripts/export_openapi.py`
- Frontend API client: `apps/web/src/lib/api-client.ts`; shared types: `packages/shared/src/types.ts`

## Core Features

- [Capture ingest](docs/features/capture-ingest.md)
- [COLMAP structure-from-motion](docs/features/sfm-reconstruction.md)
- [Splat / NeRF staging](docs/features/splat-staging.md)
- [Point-cloud preview](docs/features/point-cloud-preview.md)
- [Versioned artifact store on B2](docs/features/capture-storage.md)
- [Captures library + dashboard](docs/features/captures-dashboard.md)
- [File Upload](docs/features/file-upload.md) and [File Browser](docs/features/file-browser.md) (kept scaffolding)

## References

- [docs/SECURITY.md](docs/SECURITY.md) — security principles and implementation
- [docs/RELIABILITY.md](docs/RELIABILITY.md) — reliability expectations
- [AGENTS.md](AGENTS.md) — architectural invariants and agent instructions
