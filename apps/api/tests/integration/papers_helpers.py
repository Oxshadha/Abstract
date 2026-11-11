"""Helpers for papers API tests: start an upload, put bytes in fake storage, finalize."""

import hashlib
from typing import Any
from uuid import uuid4

from httpx import Response

from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi

MINIMAL_PDF = b"%PDF-1.7\n%test\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def new_user() -> str:
    return f"user_{uuid4().hex}"


async def start_upload(api: PapersApi, user: str, data: bytes, **overrides: Any) -> str:
    body: dict[str, Any] = {
        "filename": "paper.pdf",
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    body.update(overrides)
    response = await api.client.post("/api/v1/papers/uploads", json=body, headers=bearer(user))
    assert response.status_code == 201, response.text
    upload_id: str = response.json()["upload_id"]
    key = api.storage.posts[-1][0]
    api.storage.objects[key] = data  # what the browser would POST to S3
    return upload_id


async def finalize(api: PapersApi, user: str, upload_id: str, key: str | None = None) -> Response:
    headers = {**bearer(user), "Idempotency-Key": key or str(uuid4())}
    return await api.client.post("/api/v1/papers", json={"upload_id": upload_id}, headers=headers)


async def upload_pdf(api: PapersApi, user: str, data: bytes = MINIMAL_PDF) -> Response:
    return await finalize(api, user, await start_upload(api, user, data))
