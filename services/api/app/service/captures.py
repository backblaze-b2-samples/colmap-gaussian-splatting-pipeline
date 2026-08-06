"""Capture lifecycle: create / read / update / delete / ingest / run.

A Capture's system of record is a JSON manifest in B2
(``captures/<id>/manifest.json``) — no database. Running orchestrates from a
background daemon thread and flips the manifest ``running -> done|failed``; the
frontend polls. The heavy COLMAP SfM runs in a SEPARATE process
(``service/sfm_runner.py``) so a native crash/hang is contained. All B2 access
goes through ``repo/`` (``repo.artifacts`` for manifests/artifacts,
``repo.frames`` for frame ingest); reconstruction compute lives in
``repo/sfm.py``.
"""

import logging
import threading
import uuid
from datetime import UTC, datetime

from app.config import settings
from app.repo import artifacts, frames
from app.types.captures import Capture, CaptureCreate, CaptureStats, CaptureUpdate
from app.types.formatting import humanize_bytes

logger = logging.getLogger(__name__)

_CAPTURES_PREFIX = "captures/"
_MANIFEST = "manifest.json"

# Shared with service/capture_runner.py, which owns the run/execute path. A
# module-level lock + set is the single-replica in-process guard so two
# concurrent POST /run requests can't both launch the same capture.
_run_lock = threading.Lock()
_running: set[str] = set()


class CaptureNotFoundError(Exception):
    def __init__(self, detail: str = "Capture not found"):
        self.detail = detail
        super().__init__(detail)


class CaptureConflictError(Exception):
    def __init__(self, detail: str = "Capture is already running"):
        self.detail = detail
        super().__init__(detail)


class CaptureValidationError(Exception):
    def __init__(self, detail: str = "Invalid capture"):
        self.detail = detail
        super().__init__(detail)


def _manifest_key(cid: str) -> str:
    return f"{_CAPTURES_PREFIX}{cid}/{_MANIFEST}"


def _prefix(cid: str) -> str:
    return f"{_CAPTURES_PREFIX}{cid}/"


def _inputs_prefix(cid: str) -> str:
    return f"{_CAPTURES_PREFIX}{cid}/inputs/"


def _now() -> datetime:
    return datetime.now(UTC)


def _save(capture: Capture) -> None:
    artifacts.put_bytes(
        _manifest_key(capture.id),
        capture.model_dump_json().encode("utf-8"),
        "application/json",
    )


def _load(cid: str) -> Capture | None:
    data = artifacts.get_bytes(_manifest_key(cid))
    return Capture.model_validate_json(data) if data is not None else None


def list_captures() -> list[Capture]:
    """Every capture, newest first. Reads each manifest under captures/."""
    out: list[Capture] = []
    for obj in artifacts.list_under(_CAPTURES_PREFIX):
        if not obj["Key"].endswith(_MANIFEST):
            continue
        data = artifacts.get_bytes(obj["Key"])
        if data is None:
            continue
        try:
            out.append(Capture.model_validate_json(data))
        except ValueError:
            logger.warning("Skipping unreadable capture manifest: %s", obj["Key"])
    out.sort(key=lambda c: c.created_at, reverse=True)
    return out


def get_capture(cid: str) -> Capture:
    capture = _load(cid)
    if capture is None:
        raise CaptureNotFoundError()
    return capture


def create_capture(payload: CaptureCreate) -> Capture:
    now = _now()
    capture = Capture(
        id=uuid.uuid4().hex,
        status="draft",
        created_at=now,
        updated_at=now,
        **payload.model_dump(),
    )
    _save(capture)
    logger.info("Capture created: id=%s name=%s", capture.id, capture.name)
    return capture


def update_capture(cid: str, payload: CaptureUpdate) -> Capture:
    capture = get_capture(cid)
    if capture.status == "running":
        raise CaptureConflictError("Cannot edit a capture while it is running")
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return capture
    updated = capture.model_copy(update={**updates, "updated_at": _now()})
    _save(updated)
    logger.info("Capture updated: id=%s fields=%s", cid, sorted(updates))
    return updated


def delete_capture(cid: str) -> None:
    get_capture(cid)  # clean 404 for a missing id
    artifacts.delete_under(_prefix(cid))  # prefix-scoped — never bucket-wide
    logger.info("Capture deleted: id=%s", cid)


def ingest_images(cid: str, files: list[tuple[str, bytes]]) -> Capture:
    """Downscale and store still frames under captures/<id>/inputs/."""
    capture = get_capture(cid)
    if capture.status == "running":
        raise CaptureConflictError("Cannot add frames while a capture is running")
    added = 0
    for name, data in files:
        try:
            jpeg, _w, _h = frames.resize_image(data, capture.max_image_dimension)
        except ValueError as exc:
            raise CaptureValidationError(str(exc)) from exc
        stem = name.rsplit("/", 1)[-1].rsplit(".", 1)[0] or f"img_{added:04d}"
        artifacts.put_bytes(f"{_inputs_prefix(cid)}{stem}.jpg", jpeg, "image/jpeg")
        added += 1
    return _finish_ingest(capture, added)


def ingest_video(cid: str, filename: str, data: bytes) -> Capture:
    """Sample a capture video into frames under captures/<id>/inputs/."""
    capture = get_capture(cid)
    if capture.status == "running":
        raise CaptureConflictError("Cannot add frames while a capture is running")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"
    try:
        sampled = frames.sample_video_frames(
            data, settings.video_frame_count, capture.max_image_dimension, ext
        )
    except ValueError as exc:
        raise CaptureValidationError(str(exc)) from exc
    for name, jpeg in sampled:
        artifacts.put_bytes(f"{_inputs_prefix(cid)}{name}", jpeg, "image/jpeg")
    return _finish_ingest(capture, len(sampled))


def _finish_ingest(capture: Capture, added: int) -> Capture:
    total = len(artifacts.list_under(_inputs_prefix(capture.id)))
    updated = capture.model_copy(
        update={
            "input_count": total,
            "status": "ready" if total > 0 else capture.status,
            "updated_at": _now(),
        }
    )
    _save(updated)
    logger.info("Capture ingest: id=%s added=%s total=%s", capture.id, added, total)
    return updated


def get_capture_stats() -> CaptureStats:
    """Aggregate capture + storage metrics for the dashboard."""
    captures = list_captures()
    by_status = {"draft": 0, "ready": 0, "running": 0, "done": 0, "failed": 0}
    for c in captures:
        by_status[c.status] = by_status.get(c.status, 0) + 1

    objs = artifacts.list_under(_CAPTURES_PREFIX)
    source_bytes = sum(o["Size"] for o in objs if "/inputs/" in o["Key"])
    artifact_objs = [
        o for o in objs if not o["Key"].endswith(_MANIFEST) and "/inputs/" not in o["Key"]
    ]
    artifact_bytes = sum(o["Size"] for o in artifact_objs)

    return CaptureStats(
        total_captures=len(captures),
        draft=by_status["draft"],
        ready=by_status["ready"],
        running=by_status["running"],
        done=by_status["done"],
        failed=by_status["failed"],
        images_ingested=sum(c.input_count for c in captures),
        sparse_points=sum(c.metrics.sparse_points for c in captures),
        artifact_count=len(artifact_objs),
        artifact_bytes=artifact_bytes,
        artifact_bytes_human=humanize_bytes(artifact_bytes),
        source_bytes=source_bytes,
        source_bytes_human=humanize_bytes(source_bytes),
    )
