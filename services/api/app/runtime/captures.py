import logging

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.config import settings
from app.service.capture_runner import run_capture
from app.service.captures import (
    CaptureConflictError,
    CaptureNotFoundError,
    CaptureValidationError,
    create_capture,
    delete_capture,
    get_capture,
    get_capture_stats,
    ingest_images,
    ingest_video,
    list_captures,
    update_capture,
)
from app.types import Capture, CaptureCreate, CaptureStats, CaptureUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


async def _read_upload(file: UploadFile) -> bytes:
    """Read an UploadFile with chunked streaming + early size rejection."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.max_file_size:
            raise HTTPException(status_code=413, detail="File too large")
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("/captures", response_model=list[Capture])
def list_captures_endpoint():
    return list_captures()


# Declared before /captures/{capture_id} so "stats" is not swallowed by the id.
@router.get("/captures/stats", response_model=CaptureStats)
def capture_stats_endpoint():
    return get_capture_stats()


@router.post("/captures", response_model=Capture, status_code=201)
def create_capture_endpoint(payload: CaptureCreate):
    return create_capture(payload)


@router.get("/captures/{capture_id}", response_model=Capture)
def get_capture_endpoint(capture_id: str):
    try:
        return get_capture(capture_id)
    except CaptureNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None


@router.patch("/captures/{capture_id}", response_model=Capture)
def update_capture_endpoint(capture_id: str, payload: CaptureUpdate):
    try:
        return update_capture(capture_id, payload)
    except CaptureNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    except CaptureConflictError as e:
        raise HTTPException(status_code=409, detail=e.detail) from None


@router.delete("/captures/{capture_id}")
def delete_capture_endpoint(capture_id: str) -> dict[str, bool | str]:
    try:
        delete_capture(capture_id)
    except CaptureNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    except RuntimeError:
        raise HTTPException(
            status_code=502, detail="Failed to delete capture from storage"
        ) from None
    return {"deleted": True, "id": capture_id}


@router.post("/captures/{capture_id}/images", response_model=Capture)
async def ingest_images_endpoint(capture_id: str, files: list[UploadFile]):
    payload: list[tuple[str, bytes]] = []
    for file in files:
        payload.append((file.filename or "frame", await _read_upload(file)))
    try:
        return await run_in_threadpool(ingest_images, capture_id, payload)
    except CaptureNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    except CaptureConflictError as e:
        raise HTTPException(status_code=409, detail=e.detail) from None
    except CaptureValidationError as e:
        raise HTTPException(status_code=400, detail=e.detail) from None


@router.post("/captures/{capture_id}/video", response_model=Capture)
async def ingest_video_endpoint(capture_id: str, file: UploadFile):
    data = await _read_upload(file)
    try:
        return await run_in_threadpool(
            ingest_video, capture_id, file.filename or "capture.mp4", data
        )
    except CaptureNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    except CaptureConflictError as e:
        raise HTTPException(status_code=409, detail=e.detail) from None
    except CaptureValidationError as e:
        raise HTTPException(status_code=400, detail=e.detail) from None


@router.post("/captures/{capture_id}/run", response_model=Capture)
def run_capture_endpoint(capture_id: str):
    try:
        return run_capture(capture_id)
    except CaptureNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    except CaptureConflictError as e:
        raise HTTPException(status_code=409, detail=e.detail) from None
    except CaptureValidationError as e:
        raise HTTPException(status_code=400, detail=e.detail) from None
