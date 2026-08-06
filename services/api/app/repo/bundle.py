"""Build the Nerfstudio / gsplat-ready bundle from a COLMAP reconstruction.

Pure geometry: takes a ``pycolmap.Reconstruction`` and produces the
``transforms.json`` (Nerfstudio convention), the sparse point arrays for the
preview render, and the exact ``ns-train`` command to run the GPU-only training
tail on a CUDA host. No B2 access and no pycolmap import at module load — numpy
is imported lazily inside the functions, mirroring the rest of ``repo/``.
"""

import json


def build_transforms(reconstruction) -> bytes:
    """Serialize a Nerfstudio ``transforms.json`` for ``reconstruction``.

    Cameras are extracted with the OPENCV model, so every camera exposes
    ``[fx, fy, cx, cy, k1, k2, p1, p2]`` and the output carries full distortion
    coefficients that gsplat / Nerfstudio read directly. Per-frame
    ``transform_matrix`` is camera-to-world in the Nerfstudio (OpenGL) axis
    convention, converted from COLMAP's world-to-camera OpenCV convention.
    """
    import numpy as np

    frames = []
    intrinsics: dict | None = None
    # Flip COLMAP/OpenCV camera axes (+X right, +Y down, +Z fwd) to Nerfstudio
    # /OpenGL (+X right, +Y up, +Z back): negate the Y and Z camera axes.
    flip = np.diag([1.0, -1.0, -1.0, 1.0])

    for image_id in sorted(reconstruction.images):
        image = reconstruction.images[image_id]
        camera = reconstruction.cameras[image.camera_id]
        if intrinsics is None:
            intrinsics = _camera_intrinsics(camera)

        w2c = np.eye(4)
        w2c[:3, :4] = np.asarray(_world_to_camera(image), dtype=float)
        c2w = np.linalg.inv(w2c) @ flip
        frames.append(
            {
                "file_path": f"images/{image.name}",
                "transform_matrix": c2w.tolist(),
            }
        )

    doc = {"camera_model": "OPENCV", **(intrinsics or {}), "frames": frames}
    return (json.dumps(doc, indent=2) + "\n").encode("utf-8")


def _camera_intrinsics(camera) -> dict:
    """Return the Nerfstudio intrinsics block for an OPENCV-model camera."""
    params = list(camera.params)
    # OPENCV: fx, fy, cx, cy, k1, k2, p1, p2. Pad defensively for other models.
    while len(params) < 8:
        params.append(0.0)
    fx, fy, cx, cy, k1, k2, p1, p2 = params[:8]
    return {
        "w": int(camera.width),
        "h": int(camera.height),
        "fl_x": float(fx),
        "fl_y": float(fy),
        "cx": float(cx),
        "cy": float(cy),
        "k1": float(k1),
        "k2": float(k2),
        "p1": float(p1),
        "p2": float(p2),
    }


def _world_to_camera(image):
    """A 3x4 world-to-camera matrix for a pycolmap Image, version-robust."""
    # pycolmap 3.x: image.cam_from_world is a Rigid3d with .matrix() -> 3x4.
    cam_from_world = getattr(image, "cam_from_world", None)
    if cam_from_world is not None and hasattr(cam_from_world, "matrix"):
        return cam_from_world.matrix()
    # Older pycolmap: qvec (w, x, y, z) + tvec.
    import numpy as np

    qvec = np.asarray(image.qvec, dtype=float)
    tvec = np.asarray(image.tvec, dtype=float)
    w, x, y, z = qvec
    rot = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
    out = np.zeros((3, 4))
    out[:3, :3] = rot
    out[:3, 3] = tvec
    return out


def point_arrays(reconstruction):
    """Return ``(xyz, rgb01)`` numpy arrays for the sparse points, for preview."""
    import numpy as np

    ids = list(reconstruction.points3D)
    if not ids:
        return np.zeros((0, 3)), None
    xyz = np.array([reconstruction.points3D[i].xyz for i in ids], dtype=float)
    try:
        rgb = np.array([reconstruction.points3D[i].color for i in ids], dtype=float)
        rgb = rgb / 255.0
    except Exception:
        rgb = None
    return xyz, rgb


def fallback_ply(reconstruction) -> bytes:
    """Minimal ASCII PLY of the sparse points if ``export_PLY`` is unavailable."""
    import numpy as np

    xyz, rgb = point_arrays(reconstruction)
    n = len(xyz)
    rgb255 = (
        (np.clip(rgb, 0, 1) * 255).astype(int)
        if rgb is not None
        else np.full((n, 3), 200, dtype=int)
    )
    header = (
        "ply\nformat ascii 1.0\n"
        f"element vertex {n}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "end_header\n"
    )
    lines = [
        f"{xyz[i, 0]} {xyz[i, 1]} {xyz[i, 2]} "
        f"{rgb255[i, 0]} {rgb255[i, 1]} {rgb255[i, 2]}"
        for i in range(n)
    ]
    return (header + "\n".join(lines) + "\n").encode("utf-8")


def train_command(bundle_prefix: str) -> str:
    """The exact command to run 3D Gaussian Splatting on the staged bundle.

    Points at the local copy of the bundle a user downloads from B2 — training
    is the GPU-only tail COLMAP's CPU SfM feeds. ``splatfacto`` is Nerfstudio's
    gsplat-backed 3DGS method.
    """
    return (
        "ns-train splatfacto --data ./bundle "
        f"# after downloading b2://{bundle_prefix} to ./bundle (needs a CUDA GPU)"
    )
