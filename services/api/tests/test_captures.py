"""Capture lifecycle tests with an in-memory fake for the B2 artifact store.

No B2 credentials and no COLMAP are needed: ``app.repo.artifacts`` is replaced
with a dict-backed store so create/read/update/delete/ingest are exercised
end-to-end at the service layer. The heavy SfM run path is covered separately
(tests/test_sfm_engine.py).
"""

import io

import pytest
from PIL import Image

from app.service import captures
from app.types.captures import CaptureCreate, CaptureUpdate


class FakeStore:
    """Minimal in-memory stand-in for repo.artifacts (key -> bytes)."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, key, data, content_type):
        self.objects[key] = data
        return len(data)

    def get_bytes(self, key):
        return self.objects.get(key)

    def list_under(self, prefix):
        return [
            {"Key": k, "Size": len(v), "LastModified": None}
            for k, v in self.objects.items()
            if k.startswith(prefix)
        ]

    def delete_under(self, prefix):
        keys = [k for k in self.objects if k.startswith(prefix)]
        for k in keys:
            del self.objects[k]
        return len(keys)

    def head_version_id(self, key):
        return None


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(captures.artifacts, "put_bytes", fake.put_bytes)
    monkeypatch.setattr(captures.artifacts, "get_bytes", fake.get_bytes)
    monkeypatch.setattr(captures.artifacts, "list_under", fake.list_under)
    monkeypatch.setattr(captures.artifacts, "delete_under", fake.delete_under)
    return fake


def _png_bytes(color=(120, 60, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buf, format="PNG")
    return buf.getvalue()


def test_create_capture_starts_as_draft(store):
    capture = captures.create_capture(
        CaptureCreate(name="facade", source_type="images", quality="medium", matcher="exhaustive")
    )
    assert capture.status == "draft"
    assert capture.input_count == 0
    # Persisted as a manifest under its own prefix.
    assert f"captures/{capture.id}/manifest.json" in store.objects


def test_ingest_images_moves_to_ready_and_stores_inputs(store):
    capture = captures.create_capture(
        CaptureCreate(name="c", source_type="images", quality="low", matcher="exhaustive")
    )
    updated = captures.ingest_images(
        capture.id, [("a.png", _png_bytes()), ("b.png", _png_bytes((10, 200, 90)))]
    )
    assert updated.status == "ready"
    assert updated.input_count == 2
    input_keys = [k for k in store.objects if f"captures/{capture.id}/inputs/" in k]
    assert len(input_keys) == 2
    assert all(k.endswith(".jpg") for k in input_keys)  # re-encoded to JPEG


def test_update_capture_changes_params(store):
    capture = captures.create_capture(
        CaptureCreate(name="old", source_type="images", quality="medium", matcher="exhaustive")
    )
    updated = captures.update_capture(
        capture.id, CaptureUpdate(name="new", quality="high")
    )
    assert updated.name == "new"
    assert updated.quality == "high"
    assert updated.matcher == "exhaustive"  # untouched


def test_run_without_frames_is_rejected(store):
    capture = captures.create_capture(
        CaptureCreate(name="empty", source_type="images", quality="low", matcher="exhaustive")
    )
    from app.service.capture_runner import run_capture

    with pytest.raises(captures.CaptureValidationError):
        run_capture(capture.id)


def test_delete_capture_is_prefix_scoped(store):
    capture = captures.create_capture(
        CaptureCreate(name="c", source_type="images", quality="low", matcher="exhaustive")
    )
    captures.ingest_images(capture.id, [("a.png", _png_bytes())])
    # An unrelated object outside this capture's prefix must survive the delete.
    store.objects["captures/other/manifest.json"] = b"{}"
    captures.delete_capture(capture.id)
    assert not any(k.startswith(f"captures/{capture.id}/") for k in store.objects)
    assert "captures/other/manifest.json" in store.objects


def test_get_missing_capture_raises_not_found(store):
    with pytest.raises(captures.CaptureNotFoundError):
        captures.get_capture("does-not-exist")


def test_stats_aggregate_across_captures(store):
    c1 = captures.create_capture(
        CaptureCreate(name="one", source_type="images", quality="low", matcher="exhaustive")
    )
    captures.ingest_images(c1.id, [("a.png", _png_bytes()), ("b.png", _png_bytes())])
    stats = captures.get_capture_stats()
    assert stats.total_captures == 1
    assert stats.images_ingested == 2
    assert stats.source_bytes > 0
