"""Headless preview rendering for a COLMAP sparse point cloud.

``matplotlib`` (Agg backend) is the primary, always-works renderer — pure CPU,
deterministic, no GL context and no browser 3D engine. A ``preview.png`` is
always produced; failures degrade to a small placeholder rather than raising, so
a finished reconstruction never fails to surface just because rendering hiccuped.

All heavy imports (``matplotlib``, ``numpy``) are LAZY, inside the functions, so
importing this module needs neither wheel. This runs inside the isolated SfM
worker process (see ``service/sfm_runner.py``); it uses matplotlib's
object-oriented API (``Figure`` + ``FigureCanvasAgg``) exclusively — never the
process-global ``pyplot`` registry, which is not thread/process-safe here.
"""

import io
import logging

logger = logging.getLogger(__name__)

# Bound render time: subsample above this many points.
_MAX_RENDER_POINTS = 40000


def render_point_cloud(points, colors=None) -> bytes:
    """Return PNG bytes for a scatter render of ``points`` (Nx3). Never raises.

    ``colors`` is an optional Nx3 array in [0, 1]; when absent, points are
    colored by depth for a readable preview.
    """
    try:
        return _render(points, colors)
    except Exception:
        logger.warning("point-cloud preview failed; writing placeholder", exc_info=True)
        return _placeholder_png()


def _render(points, colors) -> bytes:
    import matplotlib

    matplotlib.use("Agg", force=True)  # headless: force non-interactive backend
    import numpy as np
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[0] == 0 or pts.shape[1] < 3:
        return _placeholder_png()

    rng = np.random.default_rng(0)  # deterministic subsampling
    if len(pts) > _MAX_RENDER_POINTS:
        idx = rng.choice(len(pts), size=_MAX_RENDER_POINTS, replace=False)
        pts = pts[idx]
        if colors is not None:
            colors = np.asarray(colors)[idx]

    fig = Figure(figsize=(6, 6), facecolor="#0b0f17")
    FigureCanvasAgg(fig)  # attach an Agg canvas; no pyplot global state
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor("#0b0f17")
    ax.set_axis_off()

    if colors is not None:
        c = np.clip(np.asarray(colors, dtype=float), 0.0, 1.0)
        ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2], c=c, s=2, linewidths=0)
    else:
        ax.scatter(
            pts[:, 0], pts[:, 1], pts[:, 2], c=pts[:, 2], cmap="viridis", s=2, linewidths=0
        )

    _equal_aspect(ax, pts, np)
    ax.view_init(elev=20, azim=-60)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor=fig.get_facecolor())
    return buf.getvalue()


def _equal_aspect(ax, pts, np) -> None:
    """Make the three axes share one scale so the shape isn't distorted."""
    mins = pts.min(axis=0)
    maxs = pts.max(axis=0)
    center = (mins + maxs) / 2
    radius = float((maxs - mins).max()) / 2 or 1.0
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)


def _placeholder_png() -> bytes:
    import matplotlib

    matplotlib.use("Agg", force=True)
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    fig = Figure(figsize=(6, 6), facecolor="#0b0f17")
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ax.set_axis_off()
    ax.text(
        0.5,
        0.5,
        "preview unavailable",
        ha="center",
        va="center",
        color="#94a3b8",
        transform=ax.transAxes,
    )
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor())
    return buf.getvalue()
