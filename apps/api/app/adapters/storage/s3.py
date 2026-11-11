"""S3 Storage adapter. Works with AWS S3 (prod) and any S3-compatible server (dev)."""

import asyncio
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import Settings
from app.ports.storage import ObjectChangedError, ObjectInfo, PresignedPost

_CHANGED = {"PreconditionFailed", "412"}
_MISSING = {"404", "NoSuchKey", "NotFound"}


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self._settings = settings
        self._client_instance: Any = None
        self._public_client_instance: Any = None

    def _build(self, endpoint_url: str | None) -> Any:
        settings = self._settings
        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=(
                settings.s3_access_key_id.get_secret_value() if settings.s3_access_key_id else None
            ),
            aws_secret_access_key=(
                settings.s3_secret_access_key.get_secret_value()
                if settings.s3_secret_access_key
                else None
            ),
            # Path-style keeps local S3-compatible servers working on plain hostnames.
            config=Config(
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=2,
                read_timeout=10,
            ),
        )

    @property
    def _client(self) -> Any:
        """Created on first use: building a boto3 client resolves credentials, which can make
        network calls (instance metadata), so it must not happen at app startup."""
        if self._client_instance is None:
            self._client_instance = self._build(self._settings.s3_endpoint_url)
        return self._client_instance

    @property
    def _public_client(self) -> Any:
        """Signs links that browsers open; only differs from `_client` in local development."""
        public = self._settings.s3_public_endpoint_url
        if public is None or public == self._settings.s3_endpoint_url:
            return self._client
        if self._public_client_instance is None:
            self._public_client_instance = self._build(public)
        return self._public_client_instance

    async def ping(self) -> None:
        await asyncio.to_thread(self._client.head_bucket, Bucket=self.bucket)

    async def ensure_bucket(self) -> None:
        """Dev convenience: create the bucket if missing. Never used in production."""
        try:
            await self.ping()
        except ClientError:
            await asyncio.to_thread(self._client.create_bucket, Bucket=self.bucket)
        # Browsers upload straight to storage (spec 004 AC2), so the web origin needs CORS.
        # Production buckets get the same rule at deployment (spec 017).
        await asyncio.to_thread(
            self._client.put_bucket_cors,
            Bucket=self.bucket,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedOrigins": self._settings.cors_origins,
                        "AllowedMethods": ["POST", "GET", "HEAD"],
                        "AllowedHeaders": ["*"],
                        # pdf.js loads the viewer's PDF with range requests (spec 008 AC2, AC7).
                        "ExposeHeaders": [
                            "Accept-Ranges",
                            "Content-Range",
                            "Content-Length",
                            "ETag",
                        ],
                        "MaxAgeSeconds": 3600,
                    }
                ]
            },
        )

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def presigned_get_url(self, key: str, expires_seconds: int = 300) -> str:
        url: str = await asyncio.to_thread(
            self._public_client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
        return url

    async def presigned_post(
        self, key: str, *, content_type: str, max_bytes: int, expires_seconds: int
    ) -> PresignedPost:
        post: dict[str, object] = await asyncio.to_thread(
            self._public_client.generate_presigned_post,
            Bucket=self.bucket,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, max_bytes],
            ],
            ExpiresIn=expires_seconds,
        )
        fields = post["fields"]
        assert isinstance(fields, dict)
        return PresignedPost(url=str(post["url"]), fields={k: str(v) for k, v in fields.items()})

    async def head(self, key: str) -> ObjectInfo | None:
        try:
            meta = await asyncio.to_thread(self._client.head_object, Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _MISSING:
                return None
            raise
        return ObjectInfo(size=int(meta["ContentLength"]), etag=str(meta["ETag"]))

    async def _get(self, key: str, *, etag: str | None, byte_range: str | None) -> bytes:
        params: dict[str, str] = {"Bucket": self.bucket, "Key": key}
        if etag:
            params["IfMatch"] = etag
        if byte_range:
            params["Range"] = byte_range
        try:
            response = await asyncio.to_thread(self._client.get_object, **params)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _CHANGED:
                raise ObjectChangedError(key) from exc
            raise
        body: bytes = await asyncio.to_thread(response["Body"].read)
        if etag and str(response.get("ETag")) != etag:  # servers that ignore If-Match
            raise ObjectChangedError(key)
        return body

    async def read_prefix(self, key: str, length: int, *, etag: str) -> bytes:
        return await self._get(key, etag=etag, byte_range=f"bytes=0-{length - 1}")

    async def get_bytes(self, key: str, *, etag: str | None = None) -> bytes:
        return await self._get(key, etag=etag, byte_range=None)

    async def delete(self, keys: list[str]) -> None:
        for start in range(0, len(keys), 1000):
            batch = [{"Key": k} for k in keys[start : start + 1000]]
            if batch:
                await asyncio.to_thread(
                    self._client.delete_objects,
                    Bucket=self.bucket,
                    Delete={"Objects": batch, "Quiet": True},
                )

    async def delete_prefix(self, prefix: str) -> int:
        def list_keys() -> list[str]:
            keys: list[str] = []
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                keys.extend(obj["Key"] for obj in page.get("Contents", []))
            return keys

        keys = await asyncio.to_thread(list_keys)
        await self.delete(keys)
        return len(keys)
