"""S3 adapter against a real S3-compatible server (the same SeaweedFS image as `make dev`).

Proves the browser upload form enforces its policy (spec 004 AC1) and that a replaced object is
detected by ETag (AC11).
"""

import asyncio
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from testcontainers.core.container import DockerContainer

from app.adapters.storage.s3 import S3Storage
from app.ports.storage import ObjectChangedError
from tests.conftest import make_settings

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]
S3_JSON = Path(__file__).resolve().parents[4] / "infra" / "seaweedfs" / "s3.json"


@pytest.fixture(scope="module")
def s3_endpoint() -> Iterator[str]:
    container = (
        DockerContainer("chrislusf/seaweedfs:4.53")
        .with_command(
            "server -dir=/data -s3 -s3.port=8333 -s3.config=/etc/s3.json "
            "-master.volumeSizeLimitMB=64"
        )
        .with_volume_mapping(str(S3_JSON), "/etc/s3.json", "ro")
        .with_exposed_ports(8333)
    )
    with container:
        url = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(8333)}"
        deadline = time.monotonic() + 60
        while True:
            try:
                httpx.get(url, timeout=1)
                break
            except httpx.HTTPError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        yield url


@pytest.fixture
async def storage(s3_endpoint: str) -> S3Storage:
    store = S3Storage(
        make_settings(
            s3_endpoint_url=s3_endpoint,
            s3_bucket="test-uploads",
            s3_access_key_id="abstract-dev",
            s3_secret_access_key="abstract-dev-secret",
        )
    )
    deadline = time.monotonic() + 60
    while True:  # the S3 gateway accepts connections slightly before it serves requests
        try:
            await store.ensure_bucket()
            return store
        except Exception:
            if time.monotonic() > deadline:
                raise
            await asyncio.sleep(0.5)


async def _post(
    storage: S3Storage, key: str, data: bytes, content_type: str, max_bytes: int = 1024
) -> httpx.Response:
    form = await storage.presigned_post(
        key, content_type="application/pdf", max_bytes=max_bytes, expires_seconds=60
    )
    fields = {**form.fields, "Content-Type": content_type}
    async with httpx.AsyncClient(timeout=30) as client:
        return await client.post(form.url, data=fields, files={"file": ("p.pdf", data)})


async def test_AC1_presigned_post_uploads_a_pdf(storage: S3Storage) -> None:
    response = await _post(storage, "quarantine/o/a.pdf", b"%PDF-1.7 hello", "application/pdf")
    assert response.status_code in (200, 201, 204), response.text
    info = await storage.head("quarantine/o/a.pdf")
    assert info is not None
    assert info.size == 14
    assert await storage.read_prefix("quarantine/o/a.pdf", 5, etag=info.etag) == b"%PDF-"


async def test_AC1_presigned_post_enforces_size_and_type(storage: S3Storage) -> None:
    too_big = await _post(storage, "quarantine/o/big.pdf", b"x" * 2048, "application/pdf")
    assert too_big.status_code >= 400
    wrong_type = await _post(storage, "quarantine/o/t.pdf", b"%PDF-", "text/html")
    assert wrong_type.status_code >= 400
    assert await storage.head("quarantine/o/big.pdf") is None
    assert await storage.head("quarantine/o/t.pdf") is None


async def test_AC11_replaced_object_is_detected(storage: S3Storage) -> None:
    await storage.put_bytes("quarantine/o/r.pdf", b"%PDF-original", "application/pdf")
    info = await storage.head("quarantine/o/r.pdf")
    assert info is not None
    await storage.put_bytes("quarantine/o/r.pdf", b"%PDF-replaced!", "application/pdf")
    with pytest.raises(ObjectChangedError):
        await storage.get_bytes("quarantine/o/r.pdf", etag=info.etag)


async def test_delete_prefix_is_idempotent(storage: S3Storage) -> None:
    for name in ("a", "b"):
        await storage.put_bytes(f"papers/o/p/{name}", b"x", "application/pdf")
    assert await storage.delete_prefix("papers/o/p/") == 2
    assert await storage.delete_prefix("papers/o/p/") == 0
    await storage.delete(["papers/o/p/missing"])


async def test_AC2_browser_links_use_the_public_endpoint(s3_endpoint: str) -> None:
    store = S3Storage(
        make_settings(
            s3_endpoint_url=s3_endpoint,
            s3_public_endpoint_url="http://public.example:9000",
            s3_bucket="test-uploads",
            s3_access_key_id="abstract-dev",
            s3_secret_access_key="abstract-dev-secret",
        )
    )
    post = await store.presigned_post(
        "quarantine/o/x.pdf", content_type="application/pdf", max_bytes=10, expires_seconds=60
    )
    assert post.url.startswith("http://public.example:9000")
    assert (await store.presigned_get_url("papers/o/p/sanitized.pdf")).startswith(
        "http://public.example:9000"
    )


async def test_AC2_bucket_allows_browser_uploads_from_the_web_origin(storage: S3Storage) -> None:
    rules = storage._client.get_bucket_cors(Bucket="test-uploads")["CORSRules"]
    assert "POST" in rules[0]["AllowedMethods"]
    assert rules[0]["AllowedOrigins"] == ["http://localhost:5173"]
