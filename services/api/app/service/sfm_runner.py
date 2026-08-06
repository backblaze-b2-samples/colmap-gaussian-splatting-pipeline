"""Run the CPU-heavy COLMAP SfM engine in an isolated 'spawn' worker process.

A native abort/segfault inside COLMAP's C++ kernels CANNOT be caught by an
in-process ``try/except`` and CANNOT be reclaimed by a thread-level timeout — it
kills/zombifies the worker. In the single-worker API that would (a) strand the
capture "running" forever and (b) take the whole API down with it. Running the
reconstruction in a separate process contains both failure modes: a native crash
kills only the child, and a genuine hang is bounded by killing the child on
timeout.

Only picklable data crosses the process boundary: the ``frames``
(``list[(name, bytes)]``) go in and an ``SfmResult`` (bytes + a Pydantic metrics
model) comes back. B2 I/O stays in the PARENT (``service/captures.py``), so the
child imports no ``boto3`` — it only runs COLMAP and renders the preview.
"""

import logging
import multiprocessing as mp
from collections.abc import Callable
from typing import Any

from app.repo.sfm import SfmResult, run_sfm

logger = logging.getLogger(__name__)

# Grace period to reap a child after it has produced a result / been killed.
_JOIN_GRACE_SECONDS = 5.0


class SfmTimeout(Exception):
    """The reconstruction exceeded its per-run time budget; child was killed."""


class SfmCrashed(Exception):
    """The worker process died (native crash/segfault) without a result."""


class SfmError(Exception):
    """The reconstruction raised an ordinary Python exception in the worker."""


def _worker(conn, fn: Callable, args: tuple, kwargs: dict) -> None:
    """Child entrypoint: run ``fn`` and ship a tagged result back over ``conn``."""
    try:
        result = fn(*args, **kwargs)
        conn.send(("ok", result))
    except Exception as exc:  # ordinary failure -> report cleanly to the parent
        conn.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        conn.close()


def _reap(proc: mp.Process) -> None:
    """Kill the child if it is still alive, then join so it is never a zombie."""
    if proc.is_alive():
        proc.kill()
    proc.join(_JOIN_GRACE_SECONDS)


def run_in_process(
    fn: Callable[..., Any],
    *,
    args: tuple = (),
    kwargs: dict | None = None,
    timeout: float,
) -> Any:
    """Run ``fn(*args, **kwargs)`` in a separate 'spawn' process, bounded by
    ``timeout`` seconds.

    Raises :class:`SfmTimeout` if the deadline passes (the child is killed
    first), :class:`SfmCrashed` if the child dies without a result, or
    :class:`SfmError` if ``fn`` raised an ordinary exception inside the child.
    """
    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_worker,
        args=(child_conn, fn, args, kwargs or {}),
        daemon=True,
    )
    proc.start()
    # Only the child writes; closing our copy lets recv see EOF if it dies.
    child_conn.close()

    status: str | None = None
    payload: Any = None
    try:
        if not parent_conn.poll(timeout):
            raise SfmTimeout("Reconstruction exceeded the per-run time limit")
        try:
            status, payload = parent_conn.recv()
        except EOFError:  # child died mid-/pre-send (native crash)
            status = None
    finally:
        parent_conn.close()
        _reap(proc)

    if status == "ok":
        return payload
    if status == "error":
        raise SfmError(str(payload))
    raise SfmCrashed(
        f"Reconstruction worker exited unexpectedly (exit code {proc.exitcode})"
    )


def run_sfm_isolated(
    frames: list[tuple[str, bytes]],
    *,
    quality: str,
    matcher: str,
    device: str | None,
    timeout: float,
) -> SfmResult:
    """Run :func:`app.repo.sfm.run_sfm` in an isolated worker process."""
    return run_in_process(
        run_sfm,
        args=(frames,),
        kwargs={"quality": quality, "matcher": matcher, "device": device},
        timeout=timeout,
    )
