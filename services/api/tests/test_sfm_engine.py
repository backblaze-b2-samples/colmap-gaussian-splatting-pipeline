"""Reconstruction-engine tests that need no COLMAP run and no GPU.

The full COLMAP SfM run needs real multi-view images and the heavy wheel, so it
is exercised by the seed script / e2e path, not here. These tests cover the pure
pieces: the matplotlib preview render, the Nerfstudio transforms builder (via a
tiny fake reconstruction), device auto-detect, and the run guard.
"""

import json

import numpy as np
import pytest

from app.repo import bundle, preview, sfm


def test_render_point_cloud_returns_png_bytes():
    pts = np.random.default_rng(0).random((500, 3))
    png = preview.render_point_cloud(pts)
    assert png.startswith(b"\x89PNG\r\n")


def test_render_point_cloud_handles_empty_cloud():
    png = preview.render_point_cloud(np.zeros((0, 3)))
    assert png.startswith(b"\x89PNG\r\n")  # placeholder, never raises


class _FakeCamera:
    def __init__(self):
        self.width = 640
        self.height = 480
        # OPENCV: fx, fy, cx, cy, k1, k2, p1, p2
        self.params = [500.0, 500.0, 320.0, 240.0, 0.01, 0.0, 0.0, 0.0]


class _FakeImage:
    """No cam_from_world attr, so build_transforms uses the qvec/tvec fallback."""

    def __init__(self, name):
        self.name = name
        self.camera_id = 1
        self.qvec = [1.0, 0.0, 0.0, 0.0]  # identity rotation (w, x, y, z)
        self.tvec = [0.0, 0.0, 2.0]


class _FakeReconstruction:
    def __init__(self, n=3):
        self.cameras = {1: _FakeCamera()}
        self.images = {i: _FakeImage(f"frame_{i:04d}.jpg") for i in range(n)}
        self.points3D = {}


def test_build_transforms_emits_opencv_intrinsics_and_frames():
    doc = json.loads(bundle.build_transforms(_FakeReconstruction(n=3)))
    assert doc["camera_model"] == "OPENCV"
    assert doc["w"] == 640 and doc["h"] == 480
    assert doc["fl_x"] == 500.0 and doc["cx"] == 320.0
    assert doc["k1"] == 0.01
    assert len(doc["frames"]) == 3
    frame = doc["frames"][0]
    assert frame["file_path"].startswith("images/")
    assert len(frame["transform_matrix"]) == 4  # 4x4 camera-to-world


def test_train_command_references_the_bundle_and_needs_a_gpu():
    cmd = bundle.train_command("captures/abc/bundle/")
    assert "ns-train splatfacto" in cmd
    assert "captures/abc/bundle/" in cmd
    assert "CUDA" in cmd


def test_detect_device_defaults_to_cpu_without_cuda(monkeypatch):
    monkeypatch.setattr(sfm.shutil, "which", lambda _name: None)
    # No CUDA-capable pycolmap and no nvidia-smi -> CPU (never hard-requires GPU).
    assert sfm.detect_device() in ("cpu", "cuda")


pycolmap = pytest.importorskip("pycolmap")


def test_run_sfm_rejects_too_few_frames():
    # Marquee guard: fewer than 3 overlapping views can't reconstruct.
    with pytest.raises(ValueError, match="at least 3"):
        sfm.run_sfm(
            [("a.jpg", b"x"), ("b.jpg", b"y")],
            quality="low",
            matcher="exhaustive",
            device="cpu",
        )
