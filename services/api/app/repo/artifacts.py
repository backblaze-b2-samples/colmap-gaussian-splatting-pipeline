"""B2 object helpers for capture manifests and derived reconstruction artifacts.

Kept out of ``b2_client.py`` (which sits near the 300-line ceiling enforced by
``tests/test_structure.py``) but still inside the ``repo/`` layer, so boto3 stays
confined here. Reuses the cached S3 client from ``b2_client`` for connection
pooling, and invalidates the same shared listing cache so a just-finished
capture's outputs show up in ``/files``, the Captures library, and the dashboard
immediately.
"""

from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings
from app.repo.b2_client import get_s3_client, invalidate_listing

# Batch ceiling for the S3 DeleteObjects API.
_DELETE_BATCH = 1000


def put_bytes(key: str, data: bytes, content_type: str) -> int:
    """Write ``data`` to ``key``. Returns the byte count. Raises RuntimeError."""
    client = get_s3_client()
    try:
        client.put_object(
            Bucket=settings.b2_bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    except (ClientError, BotoCoreError) as e:
        raise RuntimeError(f"B2 put failed for '{key}': {e}") from e
    invalidate_listing()
    return len(data)


def get_bytes(key: str) -> bytes | None:
    """Download an object's body, or None if it does not exist.

    Raises RuntimeError on any S3 failure other than a 404.
    """
    client = get_s3_client()
    try:
        response = client.get_object(Bucket=settings.b2_bucket_name, Key=key)
        return response["Body"].read()
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey"):
            return None
        raise RuntimeError(f"B2 get failed for '{key}': {e}") from e
    except BotoCoreError as e:
        raise RuntimeError(f"B2 get failed for '{key}': {e}") from e


def list_under(prefix: str) -> list[dict]:
    """Every object under ``prefix`` (paginated). Raises RuntimeError."""
    client = get_s3_client()
    items: list[dict] = []
    kwargs: dict = {
        "Bucket": settings.b2_bucket_name,
        "Prefix": prefix,
        "MaxKeys": 1000,
    }
    try:
        while True:
            response = client.list_objects_v2(**kwargs)
            items.extend(response.get("Contents", []))
            if not response.get("IsTruncated"):
                break
            kwargs["ContinuationToken"] = response["NextContinuationToken"]
    except (ClientError, BotoCoreError) as e:
        raise RuntimeError(f"B2 list failed for '{prefix}': {e}") from e
    return items


def head_version_id(key: str) -> str | None:
    """The current object's B2 version id, or None if versioning is off / 404.

    Never raises for the "no version info" case: a bucket with versioning
    suspended simply omits ``VersionId``, and the artifact list degrades to
    showing no versions rather than erroring.
    """
    client = get_s3_client()
    try:
        response = client.head_object(Bucket=settings.b2_bucket_name, Key=key)
    except (ClientError, BotoCoreError):
        return None
    version = response.get("VersionId")
    # B2 returns the literal "null" for objects in an unversioned bucket.
    return version if version and version != "null" else None


def list_versions(prefix: str) -> dict[str, list[str]]:
    """Map each key under ``prefix`` to its B2 object version ids, newest first.

    Degrades gracefully: on any S3 error or a bucket with versioning suspended,
    returns an empty map instead of raising, so the UI simply shows no version
    history rather than failing the whole capture-detail request.
    """
    client = get_s3_client()
    versions: dict[str, list[str]] = {}
    kwargs: dict = {"Bucket": settings.b2_bucket_name, "Prefix": prefix, "MaxKeys": 1000}
    try:
        while True:
            response = client.list_object_versions(**kwargs)
            for entry in response.get("Versions", []):
                vid = entry.get("VersionId")
                if vid and vid != "null":
                    versions.setdefault(entry["Key"], []).append(vid)
            if not response.get("IsTruncated"):
                break
            kwargs["KeyMarker"] = response.get("NextKeyMarker")
            kwargs["VersionIdMarker"] = response.get("NextVersionIdMarker")
    except (ClientError, BotoCoreError):
        return {}
    return versions


def delete_under(prefix: str) -> int:
    """Delete every object under ``prefix``. Returns the count deleted.

    SAFETY: the caller MUST pass a specific, slash-terminated prefix (e.g.
    ``captures/<id>/``). An empty or non-``/``-terminated prefix is refused so a
    bug can never issue a bucket-wide delete. Raises RuntimeError on S3 failure.
    """
    if not prefix or not prefix.endswith("/"):
        raise ValueError("delete_under requires a non-empty prefix ending in '/'")
    client = get_s3_client()
    keys = [{"Key": obj["Key"]} for obj in list_under(prefix)]
    if not keys:
        return 0
    deleted = 0
    try:
        for start in range(0, len(keys), _DELETE_BATCH):
            batch = keys[start : start + _DELETE_BATCH]
            client.delete_objects(
                Bucket=settings.b2_bucket_name,
                Delete={"Objects": batch, "Quiet": True},
            )
            deleted += len(batch)
    except (ClientError, BotoCoreError) as e:
        raise RuntimeError(f"B2 delete failed for '{prefix}': {e}") from e
    invalidate_listing()
    return deleted
