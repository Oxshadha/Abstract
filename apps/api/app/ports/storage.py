"""Storage port: S3-compatible object storage (S3 in prod, a local S3-compatible server in dev)."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PresignedPost:
    url: str
    fields: dict[str, str]


@dataclass(frozen=True)
class ObjectInfo:
    size: int
    etag: str


class ObjectChangedError(Exception):
    """The object no longer matches the version recorded earlier (spec 004 AC11)."""


@runtime_checkable
class Storage(Protocol):
    async def ping(self) -> None:
        """Raise if the bucket is unreachable."""
        ...

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...

    async def presigned_get_url(self, key: str, expires_seconds: int = 300) -> str: ...

    async def presigned_post(
        self, key: str, *, content_type: str, max_bytes: int, expires_seconds: int
    ) -> PresignedPost:
        """A browser upload form for exactly `key`, limited to 1 B..max_bytes of content_type."""
        ...

    async def head(self, key: str) -> ObjectInfo | None:
        """Size and ETag, or None when the object does not exist."""
        ...

    async def read_prefix(self, key: str, length: int, *, etag: str) -> bytes:
        """The first `length` bytes; raises ObjectChangedError if the ETag differs."""
        ...

    async def get_bytes(self, key: str, *, etag: str | None = None) -> bytes:
        """Whole object; with `etag`, raises ObjectChangedError if it was replaced."""
        ...

    async def delete(self, keys: list[str]) -> None:
        """Delete keys (missing keys are ignored, so cleanup is idempotent)."""
        ...

    async def delete_prefix(self, prefix: str) -> int:
        """Delete every object under `prefix`; returns how many were deleted."""
        ...
