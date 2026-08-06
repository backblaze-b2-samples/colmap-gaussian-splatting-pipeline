"""Run path for a Capture: launch COLMAP SfM and persist its artifacts to B2.

Split out of ``service/captures.py`` to keep each module under the 300-line
structural ceiling. Reuses that module's B2-backed manifest store
(``_load``/``_save``) and the shared in-process run guard, and owns the heavy
side of a run: downloading input frames, invoking the isolated SfM worker, and
writing the sparse model, staged bundle, and preview back under the capture's
own prefix. The compute itself runs in a SEPARATE process
(``service/sfm_runner.py``) so a native COLMAP crash/hang can't wedge the API.
"""

import logging
import threading
import time

from app.config import settings
from app.repo import artifacts
from app.repo.sfm import detect_device
from app.service.captures import (
    CaptureConflictError,
    CaptureValidationError,
    _inputs_prefix,
    _load,
    _now,
    _prefix,
    _run_lock,
    _running,
    _save,
    get_capture,
)
from app.service.sfm_runner import (
    SfmCrashed,
    SfmError,
    SfmTimeout,
    run_sfm_isolated,
)
from app.types.captures import Capture, CaptureArtifact, CaptureStage
from app.types.formatting import humanize_bytes

logger = logging.getLogger(__name__)


def run_capture(cid: str) -> Capture:
    """Mark a capture running and launch COLMAP SfM in a background thread."""
    capture = get_capture(cid)
    if capture.input_count <= 0:
        raise CaptureValidationError("Add capture frames before running")
    with _run_lock:
        if capture.status == "running" or cid in _running:
            raise CaptureConflictError()
        _running.add(cid)
    now = _now()
    started = capture.model_copy(
        update={
            "status": "running",
            "error": None,
            # Reset on every (re-)run so the timer counts from THIS run's start.
            "started_at": now,
            "updated_at": now,
        }
    )
    _save(started)
    threading.Thread(target=_execute, args=(cid,), daemon=True).start()
    logger.info("Capture run started: id=%s", cid)
    return started


def _execute(cid: str) -> None:
    try:
        capture = _load(cid)
        if capture is None:  # deleted between run_capture() and here
            return
        input_frames: list[tuple[str, bytes]] = []
        for obj in artifacts.list_under(_inputs_prefix(cid)):
            data = artifacts.get_bytes(obj["Key"])
            if data is not None:
                input_frames.append((obj["Key"].rsplit("/", 1)[-1], data))
        source_bytes = sum(len(d) for _, d in input_frames)

        def _persist_stages(snapshot: list[dict]) -> None:
            # One cheap manifest write per stage transition, so the detail view's
            # timeline advances live while the run is still "running".
            live = _load(cid)
            if live is None:  # deleted mid-run
                return
            stages = [CaptureStage.model_validate(s) for s in snapshot]
            _save(live.model_copy(update={"stages": stages, "updated_at": _now()}))

        started_at = time.monotonic()
        result = run_sfm_isolated(
            input_frames,
            quality=capture.quality,
            matcher=capture.matcher,
            device=detect_device(),
            timeout=settings.capture_run_timeout_seconds,
            on_progress=_persist_stages,
        )
        elapsed = time.monotonic() - started_at
        written = _write_artifacts(cid, result, dict(input_frames))
        metrics = result.metrics.model_copy(
            update={
                "source_bytes": source_bytes,
                "artifact_bytes": written["bytes"],
                "duration_seconds": round(elapsed, 1),
            }
        )
        done = _load(cid)
        if done is None:  # deleted mid-run
            return
        _save(
            done.model_copy(
                update={
                    "status": "done",
                    "updated_at": _now(),
                    "metrics": metrics,
                    "stages": result.stages,
                    "artifacts": written["artifacts"],
                    "preview_key": written["preview_key"],
                    "train_command": result.train_command.replace(
                        "captures/<id>/bundle/", f"{_prefix(cid)}bundle/"
                    ),
                }
            )
        )
        logger.info(
            "Capture done: id=%s registered=%s points=%s",
            cid,
            metrics.registered_images,
            metrics.sparse_points,
        )
    except SfmTimeout:
        _mark_failed(cid, "Reconstruction exceeded the per-run time limit")
    except SfmCrashed as exc:
        logger.warning("Capture worker crashed: id=%s err=%s", cid, exc)
        _mark_failed(cid, "Reconstruction failed unexpectedly (worker crashed)")
    except SfmError as exc:
        _mark_failed(cid, str(exc))
    except Exception as exc:
        logger.warning("Capture failed: id=%s err=%s", cid, exc)
        _mark_failed(cid, str(exc))
    finally:
        with _run_lock:
            _running.discard(cid)


def _write_artifacts(cid: str, result, frame_bytes: dict[str, bytes]) -> dict:
    prefix = _prefix(cid)
    out: list[CaptureArtifact] = []
    total = 0

    def emit(name: str, kind: str, key: str, data: bytes, ctype: str) -> None:
        nonlocal total
        size = artifacts.put_bytes(key, data, ctype)
        total += size
        out.append(
            CaptureArtifact(
                name=name,
                kind=kind,
                key=key,
                size_bytes=size,
                size_human=humanize_bytes(size),
                version_id=artifacts.head_version_id(key),
            )
        )

    emit("sparse_cloud", "cloud", f"{prefix}sparse/points.ply", result.points_ply, "application/octet-stream")
    emit("transforms", "bundle", f"{prefix}bundle/transforms.json", result.transforms_json, "application/json")
    if result.cameras_txt:
        emit("cameras", "model", f"{prefix}sparse/cameras.txt", result.cameras_txt, "text/plain")
    if result.images_txt:
        emit("images_model", "model", f"{prefix}sparse/images.txt", result.images_txt, "text/plain")

    # Stage the registered frames the transforms.json references, so the bundle
    # is a self-contained gsplat/Nerfstudio input.
    for name in result.registered_frame_names:
        data = frame_bytes.get(name)
        if data is not None:
            artifacts.put_bytes(f"{prefix}bundle/images/{name}", data, "image/jpeg")
            total += len(data)

    preview_key = f"{prefix}previews/preview.png"
    emit("preview", "image", preview_key, result.preview_png, "image/png")
    return {"artifacts": out, "bytes": total, "preview_key": preview_key}


def _mark_failed(cid: str, detail: str) -> None:
    capture = _load(cid)
    if capture is None:
        return
    _save(capture.model_copy(update={"status": "failed", "error": detail, "updated_at": _now()}))
