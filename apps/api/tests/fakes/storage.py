"""In-memory Storage for API tests (the S3 adapter has its own integration test)."""

import hashlib

from app.ports.storage import ObjectChangedError, ObjectInfo, PresignedPost


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.posts: list[tuple[str, int, int]] = []

    @staticmethod
    def etag(data: bytes) -> str:
        return f'"{hashlib.md5(data, usedforsecurity=False).hexdigest()}"'

    async def ping(self) -> None:
        return None

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    async def presigned_get_url(self, key: str, expires_seconds: int = 300) -> str:
        return f"https://s3.test/{key}?expires={expires_seconds}"

    async def presigned_post(
        self, key: str, *, content_type: str, max_bytes: int, expires_seconds: int
    ) -> PresignedPost:
        self.posts.append((key, max_bytes, expires_seconds))
        return PresignedPost(
            url="https://s3.test/bucket",
            fields={"key": key, "Content-Type": content_type, "policy": "p"},
        )

    async def head(self, key: str) -> ObjectInfo | None:
        data = self.objects.get(key)
        return None if data is None else ObjectInfo(size=len(data), etag=self.etag(data))

    async def get_bytes(self, key: str, *, etag: str | None = None) -> bytes:
        data = self.objects[key]
        if etag is not None and self.etag(data) != etag:
            raise ObjectChangedError(key)
        return data

    async def read_prefix(self, key: str, length: int, *, etag: str) -> bytes:
        return (await self.get_bytes(key, etag=etag))[:length]

    async def delete(self, keys: list[str]) -> None:
        for k in keys:
            self.objects.pop(k, None)

    async def delete_prefix(self, prefix: str) -> int:
        keys = [k for k in self.objects if k.startswith(prefix)]
        await self.delete(keys)
        return len(keys)
