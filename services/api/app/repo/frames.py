"""Frame ingest helpers: sample a capture video into frames, and downscale
still images before COLMAP sees them.

Pure, in-memory compute (bytes in, bytes out). No B2 access — that stays in
``repo/artifacts.py``. The heavy wheels (``imageio``/``imageio-ffmpeg`` and
``PIL``) are imported LAZILY inside the functions so importing this module —
and therefore ``from main import app``, test collection, and
``pnpm contract:export`` — never needs them installed.
"""

import io

# Still-image extensions COLMAP's SIFT extractor reads.
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "tif", "tiff", "bmp"}
VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm", "m4v"}


def is_image(filename: str) -> bool:
    return _ext(filename) in IMAGE_EXTENSIONS


def is_video(filename: str) -> bool:
    return _ext(filename) in VIDEO_EXTENSIONS


def _ext(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def resize_image(data: bytes, max_dimension: int) -> tuple[bytes, int, int]:
    """Downscale ``data`` so its longest side is <= ``max_dimension``.

    Returns ``(jpeg_bytes, width, height)``. Re-encodes to JPEG so COLMAP gets a
    consistent, feature-rich input regardless of the source format. A tiny image
    is returned unchanged in size (only re-encoded). Raises ValueError on an
    unreadable image.
    """
    from PIL import Image  # lazy: heavy wheel, not needed at import time

    try:
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            w, h = img.size
            longest = max(w, h)
            if longest > max_dimension:
                scale = max_dimension / float(longest)
                img = img.resize(
                    (max(1, round(w * scale)), max(1, round(h * scale))),
                    Image.LANCZOS,
                )
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=92)
            return out.getvalue(), img.size[0], img.size[1]
    except Exception as exc:
        raise ValueError(f"Could not read image: {exc}") from exc


# Cap frames read from an unknown-length clip so a huge video can't blow memory.
_MAX_SCAN_FRAMES = 5000


def sample_video_frames(
    data: bytes, count: int, max_dimension: int, ext: str = "mp4"
) -> list[tuple[str, bytes]]:
    """Sample ``count`` frames spread evenly across a capture video.

    Uses the bundled static ffmpeg from ``imageio-ffmpeg`` (keyless — never a
    system ffmpeg) via imageio's FFMPEG plugin. Returns
    ``[(frame_name, jpeg_bytes), ...]`` with frames already downscaled to
    ``max_dimension``. Raises ValueError on a video that cannot be read or
    yields no frames.
    """
    import tempfile
    from pathlib import Path

    import imageio.v3 as iio  # lazy

    if count < 2:
        count = 2
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"capture.{ext or 'mp4'}"
        src.write_bytes(data)
        total = _estimate_frame_count(iio, src)
        step = max(1, total // count) if total else 1
        try:
            selected: list = []
            for idx, frame in enumerate(iio.imiter(str(src), plugin="FFMPEG")):
                if idx % step == 0:
                    selected.append(frame)
                    if len(selected) >= count:
                        break
                if idx >= _MAX_SCAN_FRAMES:
                    break
        except Exception as exc:
            raise ValueError(f"Could not sample video frames: {exc}") from exc

    if not selected:
        raise ValueError("No frames could be sampled from the video")

    from PIL import Image  # lazy

    out: list[tuple[str, bytes]] = []
    for i, arr in enumerate(selected):
        buf = io.BytesIO()
        img = Image.fromarray(arr).convert("RGB")
        w, h = img.size
        longest = max(w, h)
        if longest > max_dimension:
            scale = max_dimension / float(longest)
            img = img.resize(
                (max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS
            )
        img.save(buf, format="JPEG", quality=92)
        out.append((f"frame_{i:04d}.jpg", buf.getvalue()))
    return out


def _estimate_frame_count(iio, src) -> int:
    """Best-effort total frame count from FFMPEG metadata (0 if unknown)."""
    try:
        meta = iio.immeta(str(src), plugin="FFMPEG")
    except Exception:
        return 0
    nframes = meta.get("nframes")
    if isinstance(nframes, int) and nframes > 0:
        return nframes
    fps = meta.get("fps")
    duration = meta.get("duration")
    if fps and duration:
        return int(float(fps) * float(duration))
    return 0
