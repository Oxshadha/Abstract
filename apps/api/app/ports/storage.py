"""Storage port: S3-compatible object storage (S3 in prod, a local S3-compatible server in dev)."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Storage(Protocol):
    async def ping(self) -> None:
        """Raise if the bucket is unreachable."""
        ...

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...

    async def presigned_get_url(self, key: str, expires_seconds: int = 300) -> str: ...
