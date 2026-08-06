"""Pydantic models for the primary entity: a photogrammetry Capture.

A Capture is a COLMAP structure-from-motion reconstruction job. Its system of
record is a JSON manifest in B2 at ``captures/<id>/manifest.json`` — there is no
database. Raw frames and every derived artifact live alongside it under the
capture's own ``captures/<id>/`` prefix.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Finite option sets — surfaced as selectors (not free text) in the create/edit
# forms, and validated at the API boundary here.
SourceType = Literal["images", "video"]
SOURCE_TYPES: tuple[SourceType, ...] = ("images", "video")

Quality = Literal["low", "medium", "high"]
QUALITIES: tuple[Quality, ...] = ("low", "medium", "high")

Matcher = Literal["exhaustive", "sequential"]
MATCHERS: tuple[Matcher, ...] = ("exhaustive", "sequential")

# draft   -> created, no frames ingested yet
# ready   -> frames ingested, ready to run (also after an edit)
# running -> COLMAP SfM in progress
# done    -> sparse model + staged bundle written to B2
# failed  -> the run errored (see .error)
CaptureStatus = Literal["draft", "ready", "running", "done", "failed"]

StageStatus = Literal["pending", "running", "done", "skipped", "failed"]

# Safe defaults surfaced as create-form hints (never autofilled).
DEFAULT_MAX_IMAGE_DIMENSION = 1600


class CaptureStage(BaseModel):
    """One step of the reconstruction pipeline, for the detail-view timeline."""

    key: str  # "ingest" | "features" | "matching" | "mapping" | ...
    label: str
    status: StageStatus = "pending"
    detail: str | None = None


class CaptureArtifact(BaseModel):
    """One derived object written back to B2 by a completed run."""

    name: str  # "sparse_cloud" | "transforms" | "preview" | ...
    kind: str  # "cloud" | "bundle" | "image" | "model"
    key: str
    size_bytes: int
    size_human: str
    # B2 object version id, when bucket versioning is enabled. None if the
    # bucket has versioning suspended (the feature degrades gracefully).
    version_id: str | None = None


class CaptureMetrics(BaseModel):
    """Numbers the reconstruction produced — drive the dashboard + detail view."""

    input_images: int = 0
    registered_images: int = 0
    sparse_points: int = 0
    observations: int = 0
    mean_reprojection_error: float = 0.0
    dense_enabled: bool = False
    device: str = "cpu"
    source_bytes: int = 0
    artifact_bytes: int = 0
    duration_seconds: float = 0.0


class CaptureParams(BaseModel):
    """The tunable inputs shared by create, edit, and the persisted manifest."""

    name: str = Field(min_length=1, max_length=120)
    source_type: SourceType = "images"
    quality: Quality = "medium"
    matcher: Matcher = "exhaustive"
    max_image_dimension: int = Field(
        default=DEFAULT_MAX_IMAGE_DIMENSION, ge=256, le=8192
    )


class CaptureCreate(CaptureParams):
    """POST /captures body."""


class CaptureUpdate(BaseModel):
    """PATCH /captures/{id} body — every field optional (partial update)."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    source_type: SourceType | None = None
    quality: Quality | None = None
    matcher: Matcher | None = None
    max_image_dimension: int | None = Field(default=None, ge=256, le=8192)


class Capture(CaptureParams):
    """Full Capture record as persisted and returned to the frontend."""

    id: str
    status: CaptureStatus
    created_at: datetime
    updated_at: datetime
    # Authoritative UTC start of the current/most-recent run — set when status
    # flips to "running" (reset on re-run), null until a capture first runs.
    # Anchors the live elapsed timer so it survives a page reload.
    started_at: datetime | None = None
    input_count: int = 0
    error: str | None = None
    metrics: CaptureMetrics = Field(default_factory=CaptureMetrics)
    stages: list[CaptureStage] = Field(default_factory=list)
    artifacts: list[CaptureArtifact] = Field(default_factory=list)
    preview_key: str | None = None
    # The exact ns-train / gsplat command to run the GPU-only training tail on a
    # CUDA host, using the staged bundle. Present once a run has staged a bundle.
    train_command: str | None = None


class CaptureStats(BaseModel):
    """Aggregate capture + storage metrics for the dashboard."""

    total_captures: int
    draft: int
    ready: int
    running: int
    done: int
    failed: int
    images_ingested: int
    sparse_points: int
    artifact_count: int
    artifact_bytes: int
    artifact_bytes_human: str
    source_bytes: int
    source_bytes_human: str
