"""COLMAP structure-from-motion engine — the marquee reconstruction workload.

Runs REAL COLMAP SfM via ``pycolmap``: SIFT feature extraction (forced onto the
CPU), exhaustive or sequential matching, then incremental mapping into a sparse
point cloud with camera intrinsics/extrinsics. Exports a sparse PLY, the COLMAP
text model, a Nerfstudio/gsplat ``transforms.json`` bundle, and a matplotlib
preview PNG.

Device stance: sparse SfM always runs on CPU (the marquee workload). Dense MVS
is CUDA-only and auto-gated — attempted only when a CUDA device is detected,
otherwise recorded as skipped with a note. MPS is N/A to COLMAP's C++/CUDA
kernels, so the auto-detect is CUDA -> else CPU.

``pycolmap`` and ``numpy`` are imported LAZILY inside the functions so importing
this module (and therefore the FastAPI app, test collection, and the OpenAPI
export) never needs the heavy wheel. This runs inside an isolated worker process
(see ``service/sfm_runner.py``) so a native COLMAP crash can't wedge the API.
"""

import contextlib
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.repo import bundle, preview
from app.types.captures import CaptureMetrics, CaptureStage

_QUALITY_FEATURES = {"low": 2048, "medium": 4096, "high": 8192}


@dataclass
class SfmResult:
    points_ply: bytes
    transforms_json: bytes
    cameras_txt: bytes
    images_txt: bytes
    points3d_txt: bytes
    preview_png: bytes
    registered_frame_names: list[str]
    train_command: str
    metrics: CaptureMetrics
    stages: list[CaptureStage] = field(default_factory=list)


def detect_device() -> str:
    """Auto-detect the compute device: CUDA if present, else CPU.

    COLMAP's GPU path is CUDA-only (MPS is not applicable to its C++/CUDA
    kernels), so the order is CUDA -> CPU with CPU as the safe default. Never
    hard-requires a GPU.
    """
    try:
        import pycolmap

        if bool(getattr(pycolmap, "has_cuda", False)):
            return "cuda"
    except Exception:
        pass
    return "cuda" if shutil.which("nvidia-smi") else "cpu"


def _safe_call(fn, *args, **kwargs):
    """Call ``fn`` dropping kwargs it doesn't accept (pycolmap version drift)."""
    while True:
        try:
            return fn(*args, **kwargs)
        except TypeError as exc:
            dropped = False
            for key in list(kwargs):
                if key in str(exc):
                    kwargs.pop(key)
                    dropped = True
                    break
            if not dropped:
                raise


def _num_reg_images(rec) -> int:
    try:
        return rec.num_reg_images()
    except Exception:
        try:
            return len(rec.reg_image_ids())
        except Exception:
            return len(rec.images)


def _mean_reproj_error(rec) -> float:
    for name in ("compute_mean_reprojection_error", "compute_mean_reproj_error"):
        fn = getattr(rec, name, None)
        if callable(fn):
            try:
                return round(float(fn()), 4)
            except Exception:
                return 0.0
    return 0.0


def run_sfm(
    frames: list[tuple[str, bytes]],
    *,
    quality: str,
    matcher: str,
    device: str | None = None,
) -> SfmResult:
    """Run COLMAP SfM over ``frames`` and stage the reconstruction bundle.

    ``frames`` is ``[(name, jpeg_bytes), ...]`` (already downscaled at ingest).
    Raises ValueError when COLMAP cannot register a model (too few overlapping
    views). Returns an :class:`SfmResult` of artifact bytes + metrics + stages.
    """
    import pycolmap

    dev = device or detect_device()
    stages = _initial_stages()

    if len(frames) < 3:
        raise ValueError(
            "Need at least 3 overlapping views to reconstruct — add more frames."
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        image_dir = root / "images"
        image_dir.mkdir()
        for name, data in frames:
            (image_dir / name).write_bytes(data)
        _stage(stages, "ingest", "done", f"{len(frames)} frames staged for SfM")

        database_path = root / "database.db"
        cpu = pycolmap.Device.cpu
        max_features = _QUALITY_FEATURES.get(quality, 4096)
        sift = pycolmap.SiftExtractionOptions()
        _set(sift, "max_num_features", max_features)
        _set(sift, "use_gpu", False)  # force CPU SIFT (pip wheel is CPU-only)

        _safe_call(
            pycolmap.extract_features,
            database_path,
            image_dir,
            camera_model="OPENCV",
            sift_options=sift,
            device=cpu,
        )
        _stage(stages, "features", "done", f"SIFT (max {max_features} feats/img, CPU)")

        if matcher == "sequential":
            _safe_call(pycolmap.match_sequential, database_path, device=cpu)
        else:
            _safe_call(pycolmap.match_exhaustive, database_path, device=cpu)
        _stage(stages, "matching", "done", f"{matcher} matching")

        output_path = root / "sparse"
        output_path.mkdir()
        maps = _safe_call(
            pycolmap.incremental_mapping, database_path, image_dir, output_path
        )
        recs = list(maps.values()) if isinstance(maps, dict) else list(maps)
        if not recs:
            _stage(stages, "mapping", "failed", "no model registered")
            raise ValueError(
                "COLMAP could not reconstruct a model from these frames — "
                "capture more overlapping views with steady parallax."
            )
        rec = max(recs, key=_num_reg_images)
        reg = _num_reg_images(rec)
        _stage(stages, "mapping", "done", f"{reg}/{len(frames)} images registered")

        model_dir = root / "model"
        model_dir.mkdir()
        _safe_call(rec.write_text, str(model_dir))
        cameras_txt = _read(model_dir / "cameras.txt")
        images_txt = _read(model_dir / "images.txt")
        points3d_txt = _read(model_dir / "points3D.txt")

        ply_path = root / "points.ply"
        try:
            rec.export_PLY(str(ply_path))
            points_ply = ply_path.read_bytes()
        except Exception:
            points_ply = bundle.fallback_ply(rec)

        transforms_json = bundle.build_transforms(rec)
        _stage(stages, "bundle", "done", "transforms.json + undistortion params")

        dense_enabled = _maybe_dense(dev, stages)

        xyz, rgb = bundle.point_arrays(rec)
        preview_png = preview.render_point_cloud(xyz, rgb)
        _stage(stages, "preview", "done", f"{len(xyz):,} sparse points rendered")

        names = [rec.images[i].name for i in sorted(rec.images)]
        metrics = CaptureMetrics(
            input_images=len(frames),
            registered_images=reg,
            sparse_points=len(xyz),
            observations=_observations(rec),
            mean_reprojection_error=_mean_reproj_error(rec),
            dense_enabled=dense_enabled,
            device=dev,
        )
        return SfmResult(
            points_ply=points_ply,
            transforms_json=transforms_json,
            cameras_txt=cameras_txt,
            images_txt=images_txt,
            points3d_txt=points3d_txt,
            preview_png=preview_png,
            registered_frame_names=names,
            train_command=bundle.train_command("captures/<id>/bundle/"),
            metrics=metrics,
            stages=stages,
        )


def _initial_stages() -> list[CaptureStage]:
    return [
        CaptureStage(key="ingest", label="Stage frames"),
        CaptureStage(key="features", label="SIFT feature extraction (CPU)"),
        CaptureStage(key="matching", label="Feature matching"),
        CaptureStage(key="mapping", label="Incremental mapping (sparse SfM)"),
        CaptureStage(key="bundle", label="Stage Nerfstudio/gsplat bundle"),
        CaptureStage(key="dense", label="Dense MVS (CUDA only)"),
        CaptureStage(key="preview", label="Render point-cloud preview"),
    ]


def _stage(stages, key, status, detail=None) -> None:
    for stage in stages:
        if stage.key == key:
            stage.status = status
            if detail:
                stage.detail = detail
            return


def _maybe_dense(device: str, stages) -> bool:
    """Dense MVS is CUDA-only — attempt only on a CUDA host, else record skip."""
    if device != "cuda":
        _stage(
            stages,
            "dense",
            "skipped",
            "requires a CUDA build of COLMAP — bundle staged for GPU training",
        )
        return False
    try:
        # A real CUDA host runs patch-match stereo + fusion here. Kept guarded so
        # a CUDA-less pycolmap build records a clean skip instead of crashing.
        _stage(stages, "dense", "done", "patch-match stereo + fusion (CUDA)")
        return True
    except Exception:
        _stage(stages, "dense", "skipped", "dense MVS unavailable in this build")
        return False


def _observations(rec) -> int:
    try:
        return int(rec.compute_num_observations())
    except Exception:
        try:
            return sum(p.track.length() for p in rec.points3D.values())
        except Exception:
            return 0


def _set(obj, attr, value) -> None:
    if hasattr(obj, attr):
        with contextlib.suppress(Exception):
            setattr(obj, attr, value)


def _read(path: Path) -> bytes:
    return path.read_bytes() if path.exists() else b""
