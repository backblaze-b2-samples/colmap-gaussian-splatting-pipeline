<!-- completed: 2026-08-06 — initial scaffold built and verified (pnpm verify green; b2-doctor clean) -->

# Build plan — `colmap-gaussian-splatting-pipeline`

Source of truth for the starter tree:
`.claude/scratch/vcsk-113a01ca-abc7-446c-ae6b-aa6ab498e0fc/` (fetched fresh in Phase 0).
Build target: `./colmap-gaussian-splatting-pipeline`.

## 1. Purpose

`colmap-gaussian-splatting-pipeline` is an end-to-end **capture-to-B2 photogrammetry
pipeline**. A user (3D artist, real-estate photographer, heritage-preservation team)
creates a **Capture** — a named reconstruction job — from an image set or a capture
video, and the app runs **COLMAP** structure-from-motion (via `pycolmap`) to produce a
sparse point cloud + camera poses, then **stages a Nerfstudio/gsplat-ready bundle**
(`transforms.json` + undistorted frames + sparse model + PLY) for downstream 3D
Gaussian Splatting / NeRF reconstruction. **Backblaze B2 is the versioned storage
layer for the whole lifecycle**: raw capture sets, SfM outputs, staged bundles, and
render/preview artifacts all live under the capture's own B2 prefix, accessed over the
**S3-compatible API** with a custom user-agent and standard `B2_*` env vars. It runs on
local OSS only — COLMAP is keyless, no second API key, B2 credentials only.

**Honesty / device stance (matches the use case's "complements standalone splat/NeRF
reconstruction tools"):** COLMAP **sparse SfM runs on CPU** and is the marquee workload
that always runs. COLMAP **dense MVS** and **gsplat/Nerfstudio training** require CUDA;
the device is auto-detected (CUDA → else CPU; MPS is N/A to COLMAP's C++/CUDA kernels).
When no CUDA device is present (the macOS/default path), the pipeline **stages** the
reconstruction bundle on B2 and emits the exact `ns-train` / `gsplat` command to run on
a GPU host, rather than faking a trained splat. This is a real pipeline whose GPU-only
tail is honestly gated, not a mock.

## 2. Architecture delta from `vibe-coding-starter-kit`

The starter kit is the ceiling — strip what this app doesn't need, keep the B2 scaffolding.

### KEEP as-is (starter contract — do not strip/rename/replace)
- **UI kit / design system**: `apps/web/src/components/ui/**` (shadcn primitives, never
  edited directly), design tokens in `apps/web/src/app/globals.css`, the `/design` page
  and its `components/design/**`.
- **Full-bucket File Explorer** (NON-NEGOTIABLE KEEP): `/files` route, `apps/web/src/app/files/`,
  `apps/web/src/components/files/**`, and the Files sidebar entry. This browses the whole
  bucket and is never removable.
- **Upload**: `/upload` route, `apps/web/src/app/upload/`, `apps/web/src/components/upload/**`,
  Upload sidebar entry. Generic B2 upload is reused as the raw-frame ingest primitive.
- **Settings**: `/settings` + `components/settings/**` (incl. `settings-form.tsx`, the
  in-repo exemplar for form UX — selectors for finite fields + create-time default hints).
- Backend layering `types → config → repo → service → runtime`, the B2 repo adapter,
  list cache, health/metrics/ratelimit runtime, structured logging, CORS ordering, the
  contract-export discipline (`docs/api/openapi.json` + `api-client` routes + `queries` +
  `api-contract.test` must agree), and all mechanical enforcement (`check:agent-docs`,
  structure tests, `verify`).
- Sidebar shell, command palette, theme provider, health banner, TanStack Query data layer.

### ADD (new for this sample)
- **Captures library** (the sample-specific asset explorer scoped to the app's OWN prefix
  `captures/`, distinct from and additional to the full-bucket File Explorer) — `/captures`.
- **Capture detail** `/captures/[id]` — stage timeline, params, sparse point-cloud preview
  image, artifact list (with B2 keys + object versions + download), and run/edit/delete/re-run actions.
- **Create Capture** flow (dialog or `/captures/new`) — the create form.
- **Reconstruction engine** in `repo/` — `pycolmap` wrapper (SfM: feature extraction →
  matching → incremental mapping → sparse PLY export → Nerfstudio `transforms.json`
  bundle), device auto-detect, dense-MVS CUDA gate. **All `pycolmap` / `matplotlib` /
  `imageio` imports are LAZY (inside functions)** so app import, test collection, and
  `contract:export` never need the heavy wheels (mirrors the starter's lazy `PIL`).
- **Capture manifest store** in `repo/` — each capture is a B2 prefix
  `captures/<id>/` holding `manifest.json` (status, stages, params, artifacts, timestamps),
  `inputs/` (raw frames), `sparse/` (COLMAP model + PLY), `bundle/` (transforms.json +
  undistorted images), `previews/` (matplotlib-rendered point-cloud PNGs). **B2 is the
  source of truth — no database.** Listing captures = list `captures/` + read manifests.
- **Point-cloud preview renderer** in `repo/` — headless **matplotlib** scatter/projection
  of the sparse cloud to a PNG stored under `previews/` (matplotlib-primary render pattern;
  no browser 3D engine dependency, robust + keyless).
- **Background job runner** — the `run` verb executes the pipeline in a threadpool
  (starter already offloads blocking B2 work); an in-process progress registry reconciles
  to the on-B2 manifest as each stage completes, so state survives restarts.
- **Domain dashboard** metrics: captures total, images ingested, sparse points reconstructed,
  artifacts + storage stored on B2, recent-captures table, a chart (points/artifacts per
  recent capture). Flows through `runtime → service → repo` + `queries.ts` (no bare fetch).

### TRIM (remove from starter — illustrative defaults this app replaces)
- Starter dashboard components tied to generic "uploads" framing
  (`components/dashboard/recent-uploads-table.tsx`, `upload-chart.tsx`, `stats-cards.tsx`)
  are **rewritten** (not deleted) to the capture-domain metrics above, reusing the same
  chart/table/stat-card primitives.
- `docs/features/metadata-extraction.md` + the on-demand rich-metadata detail path are
  **out of the domain** — trim the feature doc to a brief note (image EXIF is still useful
  for captures) OR repurpose to "frame metadata"; do NOT remove the `/files` detail route
  (part of the kept File Explorer contract). Prefer: keep the code, retarget the doc.
- Nothing else is removed. The File Explorer, Upload, and UI kit stay per the KEEP contract
  (recorded tension note: this sample is capture-centric, but the full-bucket explorer is
  kept anyway per the non-negotiable rule).

## 3. B2 surface (S3-compatible API only — no b2-native)

| Operation | Where | Purpose |
|---|---|---|
| `put_object` / multipart upload | repo (ingest, artifact writes, manifest writes) | store raw frames, sparse model, PLY, bundle, previews, manifest.json |
| `list_objects_v2` (paginated) | repo (list cache + captures store) | full-bucket explorer + list `captures/` prefixes |
| `get_object` | repo | read manifest.json, fetch artifacts server-side |
| `head_object` | repo | artifact size/type/existence |
| `delete_object` / `delete_objects` | repo | delete a capture — **scoped strictly to `captures/<id>/`** |
| `generate_presigned_url` | repo | browser downloads + inline preview-image URLs |
| `list_object_versions` | repo (new) | show B2 object versions per artifact ("every input/output versioned on B2") — degrades gracefully if bucket versioning is suspended |

**No b2-native API anywhere** (parent CLAUDE.md default). Custom UA
`b2-colmap-gsplat-pipeline` set via `Config(user_agent_extra=...)` on the single cached
S3 client. Delete is prefix-scoped to the capture; never a bucket-wide wipe.

## 4. Key features (seed README + `docs/features/<feature>.md`)

All features are **`deployment: local`** — COLMAP/`pycolmap` is keyless OSS running
on-device; **no external API provider, no LLM, no Genblaze** (the description names none
and says "no second API key, B2 credentials only"). Local heavy workload inherits the
CPU-default / GPU-autodetect hard rule: **CUDA → else CPU** (MPS N/A to COLMAP).

1. **Capture ingest** (`docs/features/capture-ingest.md`) — create a capture from an
   image set (bulk upload) or a capture video (server samples frames via bundled
   `imageio-ffmpeg`, keyless). Raw frames land under `captures/<id>/inputs/` on B2.
   *deployment: local.*
2. **COLMAP structure-from-motion** (`docs/features/sfm-reconstruction.md`) — real
   `pycolmap` SfM on CPU: SIFT extraction (forced CPU), exhaustive/sequential matching,
   incremental mapping → sparse point cloud + camera intrinsics/extrinsics. Dense MVS is
   CUDA-gated (auto-skipped with a recorded note on CPU hosts). *deployment: local, GPU-autodetect.*
3. **Splat/NeRF staging** (`docs/features/splat-staging.md`) — export a Nerfstudio/gsplat-ready
   bundle (`transforms.json`, undistorted frames, sparse model, `points.ply`) to
   `captures/<id>/bundle/`, plus the exact `ns-train`/`gsplat` command to run on a GPU host.
   When CUDA IS present, training runs; otherwise the bundle is staged. *deployment: local, GPU-autodetect.*
4. **Point-cloud preview** (`docs/features/point-cloud-preview.md`) — headless matplotlib
   render of the sparse cloud to a PNG artifact on B2, shown in the capture detail view.
   *deployment: local.*
5. **Versioned artifact store on B2** (`docs/features/capture-storage.md`) — every input
   and derived output lives under the capture's B2 prefix; the UI surfaces object versions
   and download links via presigned URLs. *deployment: local.*
6. **Captures library + dashboard** (`docs/features/captures-dashboard.md`) — scoped
   explorer of the app's own captures + domain metrics.

### Primary-entity lifecycle (UI completeness — MANDATORY)

**Primary entity: `Capture`** (a reconstruction job). The UI exposes ALL lifecycle verbs
— **create / read / edit / delete / run** — and Phase 2 builds every one. No verb is
omitted; `omitted_ui_verbs` is empty.

| Verb | Endpoint | UI |
|---|---|---|
| create | `POST /captures` (+ `POST /captures/{id}/images`, `POST /captures/{id}/video`) | Create-Capture dialog/page |
| read | `GET /captures`, `GET /captures/{id}` | Captures library + detail view |
| edit | `PATCH /captures/{id}` (rename, adjust params) | Edit dialog on detail view |
| delete | `DELETE /captures/{id}` (prefix-scoped) | Delete action (AlertDialog confirm) |
| run | `POST /captures/{id}/run` | Run / Re-run button on detail view |

### Form UX conventions (create/edit)

Exemplar: `apps/web/src/components/settings/settings-form.tsx`.
- **Finite-value fields use selectors** (`Select` / `RadioGroup`), never free text — both
  create AND edit:
  - `source_type` → RadioGroup: `Image set` | `Capture video`.
  - `quality` (SfM preset) → Select: `Low (fast)` | `Medium` | `High`.
  - `matcher` → Select: `Exhaustive (small sets)` | `Sequential (video/ordered)`.
- Free-text: `name` (Input), `max_image_dimension` (numeric Input with sane bounds).
- **Create-form default hints** (placeholder / `FormDescription` guidance only — never an
  autofill button): name → e.g. `heritage-facade-01`; source_type default `Image set`;
  quality default `Medium`; matcher default `Exhaustive`; max_image_dimension default
  `1600` with guidance "downscales large frames so CPU SfM finishes quickly". Edit form
  opens pre-filled from the real capture.

## 5. Doc transforms

- **Rewrite**: `README.md` (whole sample story), `ARCHITECTURE.md` (add capture pipeline,
  reconstruction engine in repo/, manifest-on-B2 design, device gating), `docs/app-workflows.md`
  (capture lifecycle journeys), `docs/features/dashboard.md` → captures dashboard.
- **Retarget (keep code)**: `docs/features/file-upload.md` (upload = raw-frame ingest
  primitive), `docs/features/file-browser.md` (full-bucket explorer, kept), `docs/features/metadata-extraction.md`
  (trim to "frame metadata" note).
- **Keep**: `docs/features/settings.md`, `docs/SECURITY.md` (update identity refs),
  `docs/RELIABILITY.md`, `docs/dev-workflows.md` (update identity + add pycolmap/heavy-dep
  note + lazy-import rationale), `_template.md`.
- **New stubs**: `capture-ingest.md`, `sfm-reconstruction.md`, `splat-staging.md`,
  `point-cloud-preview.md`, `capture-storage.md`, `captures-dashboard.md`.
- **AGENTS.md**: update Repository Map + §2 starter contract (add Captures as the primary
  feature; keep Files/Upload/UI-kit as kept scaffolding) while preserving ALL mechanical
  invariants, the secret-handling section, env-file rules, vercel-button rule, and command
  list so `pnpm check:agent-docs` stays green. Keep shims (`CLAUDE.md`, `GEMINI.md`,
  `.github/copilot-instructions.md`) as thin pointers.
- Move this plan to `docs/exec-plans/completed/initial-scaffold.md` on PASS.

## 6. Rename table

| From (`vibe-coding-starter-kit`) | To (`colmap-gaussian-splatting-pipeline`) |
|---|---|
| kebab id `vibe-coding-starter-kit` | `colmap-gaussian-splatting-pipeline` |
| Title Case `Vibe Coding Starter Kit` | `COLMAP Gaussian Splatting Pipeline` |
| root `package.json` name `vibe-coding-starter-kit` | `colmap-gaussian-splatting-pipeline` |
| `@vibe-coding-starter-kit/web` | `@colmap-gaussian-splatting-pipeline/web` |
| `@vibe-coding-starter-kit/shared` | `@colmap-gaussian-splatting-pipeline/shared` (update every import of the shared pkg) |
| `APP_NAME` (`app-config.ts`) = "Vibe Coding Starter Kit" | "COLMAP Gaussian Splatting Pipeline" |
| `APP_DESCRIPTION` | "Capture-to-B2 photogrammetry pipeline: COLMAP SfM + Gaussian Splatting / NeRF staging, every artifact versioned on Backblaze B2" |
| `API_TITLE` / `API_DESCRIPTION` (`main.py`) | "COLMAP Gaussian Splatting Pipeline API" / capture-pipeline description |
| S3 `user_agent_extra` `b2ai-oss-start` | `b2-colmap-gsplat-pipeline` |
| UTM `utm_content=b2ai-oss-start` (sidebar footer) | `utm_content=b2-colmap-gsplat-pipeline` |
| infra image/service slugs (`infra/railway/web.railway.json`, `vercel.json`) `vibe-coding-starter-kit` | `colmap-gaussian-splatting-pipeline` |
| header `pageTitles` map | add `"/captures": "Captures"` (route already derives titles via `deriveTitleFromPath`) |
| `docs/api/openapi.json` `title` + any refs | regenerate via `pnpm contract:export` after route changes |

### Env-var standardization (parent Standard #3 — b2-doctor enforced)

Rename starter env vars to the standard names in `settings.py`, `main.py`
(`REQUIRED_B2_SETTINGS` + placeholder set), `b2_client.py`, `.env.example`,
`scripts/doctor.mjs`, and all docs:

| Starter | Standard |
|---|---|
| `B2_KEY_ID` | `B2_APPLICATION_KEY_ID` |
| `B2_APPLICATION_KEY` | `B2_APPLICATION_KEY` (unchanged) |
| `B2_BUCKET_NAME` | `B2_BUCKET_NAME` (unchanged) |
| (none) | `B2_REGION` (add; default `us-east-005`) |
| `B2_PUBLIC_URL` | `B2_PUBLIC_URL_BASE` |
| `B2_ENDPOINT` | keep `B2_ENDPOINT` (boto3 needs `endpoint_url`); derive from `B2_REGION` when unset |

Settings fields become `b2_application_key_id`, `b2_application_key`, `b2_bucket_name`,
`b2_region`, `b2_endpoint`, `b2_public_url_base`. `.env.example` uses placeholders only
(the deny-b2-secrets hook blocks real `K00…`/`005…` values); real creds only in `.env`.

## 7. Backend dependencies to add (`requirements.txt`, lower-bound pins; regenerate `requirements.lock`)

- `pycolmap>=3.10,<3.12` — COLMAP SfM (prebuilt macOS/linux wheels; **lazy-imported in repo/**).
- `numpy>=1.26,<2` — point math (numpy<2 to stay compatible with the ML wheels).
- `matplotlib>=3.8` — headless point-cloud preview render (`Agg` backend; lazy-imported).
- `imageio>=2.34` + `imageio-ffmpeg>=0.5` — keyless video frame sampling (bundled static
  ffmpeg; Homebrew ffmpeg is slim — do NOT depend on a system ffmpeg).
- `plyfile>=1.0` — sparse PLY read/write.
- Keep `Pillow`, `boto3`, FastAPI stack. **Pin everything** (unpinned ML deps are a known
  false-green class). Heavy wheels must NOT be import-time deps of `main`/tests/contract
  export — lazy import only.

## 8. Structural / verification guardrails (keep `pnpm verify` green)

- No `boto3` and no heavy-ML imports outside `repo/` (structure test); business logic in
  `service/`, routes thin in `runtime/`; files < 300 lines; typed Pydantic models at the
  boundary; structured logging (no `print`).
- Every new route updates `runtime/*`, `lib/api-client.ts` (`API_CLIENT_ROUTES`),
  `lib/queries.ts`, and `docs/api/openapi.json` (`pnpm contract:export`); backend-only
  routes also go in `SERVER_ONLY_OPERATIONS` in `api-contract.test.ts`.
- New Pydantic types in `types/`: `Capture`, `CaptureStatus` (enum), `CaptureStage`,
  `CaptureParams`, `CaptureArtifact`, `CaptureStats`.
- Tests: engine unit tests use a **tiny synthetic fixture and mock/skip `pycolmap`** when
  the wheel is absent (mark heavy tests `skipif`), so `pnpm verify:api` passes credential-
  and GPU-free. Manifest store + service tests with a faked S3 client. Frontend: queries +
  a capture-card/list unit test. Keep contract + structure tests green.
- **Optional seed** `services/api/scripts/seed_demo.py` (idempotent, prefix-scoped): paints
  a feature-rich synthetic multi-view set, uploads as one capture, runs real CPU SfM — for
  later screenshot/verify steps. NOT run by `verify`. Document under `pnpm run` scripts.

## 9. Notes / open tensions

- Full-bucket File Explorer kept despite this being a capture-centric app (non-negotiable
  KEEP rule); the Captures library is the scoped, domain view added alongside it.
- Real gsplat/NeRF *training* is GPU-only; on the default (macOS/CPU) path the pipeline
  stages the bundle + command instead of faking a trained splat — honest to the use case.
- COLMAP dense MVS is CUDA-only; sparse SfM (the marquee workload) runs on CPU.
- Synthetic seed avoids shipping binary assets and keeps the demo keyless and reproducible.
