"""Seed one demo Capture and run a real CPU reconstruction — screenshot helper.

Renders a feature-rich SYNTHETIC multi-view set (textured billboards on a 3D
room corner, orbited by a pinhole camera) so no binary assets ship and the demo
stays keyless and reproducible. Then it creates a Capture, ingests the frames,
and runs the REAL COLMAP pipeline through the service layer. Idempotent and
prefix-scoped to its own capture; NOT run by `pnpm verify`.

Usage (needs a populated repo-root .env with B2 credentials):
    services/api/.venv/bin/python services/api/scripts/seed_demo.py
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from PIL import Image

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
load_dotenv(REPO_ROOT / ".env")

IMG_W, IMG_H = 900, 600
FOCAL = 800.0
N_VIEWS = 28
RNG = np.random.default_rng(7)


def _out(message: str) -> None:
    sys.stdout.write(message + "\n")


def _texture(size: int = 256) -> Image.Image:
    """A high-frequency, feature-rich RGB texture (blobs on colored noise)."""
    base = (RNG.random((size, size, 3)) * 70 + 40).astype(np.uint8)
    img = Image.fromarray(base, "RGB")
    px = img.load()
    for _ in range(220):
        cx, cy = RNG.integers(0, size, size=2)
        r = int(RNG.integers(6, 22))
        color = tuple(int(c) for c in RNG.integers(60, 255, size=3))
        for x in range(max(0, cx - r), min(size, cx + r)):
            for y in range(max(0, cy - r), min(size, cy + r)):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    px[x, y] = color
    return img


def _find_coeffs(dst, src):
    """PIL PERSPECTIVE coeffs mapping output(dst) corners to input(src) corners."""
    a = []
    b = []
    for (dx, dy), (sx, sy) in zip(dst, src, strict=False):
        a.append([dx, dy, 1, 0, 0, 0, -sx * dx, -sx * dy])
        a.append([0, 0, 0, dx, dy, 1, -sy * dx, -sy * dy])
        b += [sx, sy]
    res = np.linalg.solve(np.asarray(a, dtype=float), np.asarray(b, dtype=float))
    return res.tolist()


# A room-corner scene: three perpendicular textured walls (non-planar -> good
# for SfM). Each quad = (4 world corners, texture).
def _scene():
    tex = [_texture() for _ in range(3)]
    walls = [
        # back wall (z = 0 plane), x in [-1,1], y in [0,2]
        [(-1, 0, 0), (1, 0, 0), (1, 2, 0), (-1, 2, 0)],
        # floor (y = 0 plane), x in [-1,1], z in [0,2]
        [(-1, 0, 0), (1, 0, 0), (1, 0, 2), (-1, 0, 2)],
        # side wall (x = -1 plane), z in [0,2], y in [0,2]
        [(-1, 0, 0), (-1, 0, 2), (-1, 2, 2), (-1, 2, 0)],
    ]
    return list(zip(walls, tex, strict=False))


def _look_at(cam, target, up=(0, 1, 0)):
    f = np.asarray(target) - np.asarray(cam)
    f = f / np.linalg.norm(f)
    r = np.cross(f, np.asarray(up, dtype=float))
    r = r / np.linalg.norm(r)
    u = np.cross(r, f)
    R = np.stack([r, u, f])  # world -> camera rows
    return R, np.asarray(cam, dtype=float)


def _project(R, C, X):
    xc = R @ (np.asarray(X, dtype=float) - C)
    if xc[2] <= 0.05:
        return None, xc[2]
    return (FOCAL * xc[0] / xc[2] + IMG_W / 2, FOCAL * xc[1] / xc[2] + IMG_H / 2), xc[2]


def _render_view(scene, R, C) -> bytes:
    frame = Image.new("RGB", (IMG_W, IMG_H), (14, 16, 22))
    drawables = []
    for corners, tex in scene:
        projected = [_project(R, C, X) for X in corners]
        if any(p is None for p, _ in projected):
            continue
        pts = [p for p, _ in projected]
        depth = float(np.mean([d for _, d in projected]))
        drawables.append((depth, pts, tex))
    for _depth, pts, tex in sorted(drawables, key=lambda t: -t[0]):
        w, h = tex.size
        src = [(0, 0), (w, 0), (w, h), (0, h)]
        try:
            coeffs = _find_coeffs(pts, src)
        except np.linalg.LinAlgError:
            continue
        layer = tex.convert("RGBA").transform(
            (IMG_W, IMG_H), Image.PERSPECTIVE, coeffs, Image.BILINEAR, fillcolor=(0, 0, 0, 0)
        )
        frame = Image.alpha_composite(frame.convert("RGBA"), layer).convert("RGB")
    buf = io.BytesIO()
    frame.save(buf, format="PNG")
    return buf.getvalue()


def _frames() -> list[tuple[str, bytes]]:
    scene = _scene()
    target = np.array([0.0, 1.0, 1.0])
    out = []
    for i in range(N_VIEWS):
        angle = -0.6 + 1.2 * i / (N_VIEWS - 1)  # sweep azimuth for parallax
        cam = target + np.array([2.6 * np.sin(angle), 0.2 * np.sin(i * 0.5), -2.6 * np.cos(angle)])
        R, C = _look_at(cam, target)
        out.append((f"view_{i:04d}.png", _render_view(scene, R, C)))
    return out


def main() -> int:
    from app.service import capture_runner, captures
    from app.types.captures import CaptureCreate

    _out("Rendering synthetic multi-view frames…")
    frames = _frames()
    capture = captures.create_capture(
        CaptureCreate(name="demo-room-corner", source_type="images", quality="medium", matcher="exhaustive")
    )
    _out(f"Created capture {capture.id}; ingesting {len(frames)} frames to B2…")
    captures.ingest_images(capture.id, frames)

    _out("Running COLMAP structure-from-motion (CPU)…")
    capture_runner.run_capture(capture.id)
    for _ in range(600):
        time.sleep(2)
        current = captures.get_capture(capture.id)
        if current.status in ("done", "failed"):
            break
    current = captures.get_capture(capture.id)
    if current.status == "done":
        m = current.metrics
        _out(
            f"DONE: {m.registered_images}/{m.input_images} images registered, "
            f"{m.sparse_points} sparse points on {m.device}. "
            f"Open /captures/{capture.id}"
        )
        return 0
    _out(f"Reconstruction {current.status}: {current.error or '(synthetic set may need more overlap)'}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
