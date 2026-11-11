"""Spec 004 AC1: pre-signed upload tickets."""

from uuid import uuid4

import pytest

from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


def upload_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {"filename": "paper.pdf", "size_bytes": 1234, "sha256": "e" * 64}
    body.update(overrides)
    return body


async def test_AC1_returns_a_presigned_post_under_the_org_prefix(api: PapersApi) -> None:
    user = f"user_{uuid4().hex}"
    response = await api.client.post(
        "/api/v1/papers/uploads", json=upload_body(), headers=bearer(user)
    )
    assert response.status_code == 201, response.text
    body = response.json()
    me = (await api.client.get("/api/v1/me", headers=bearer(user))).json()
    key, max_bytes, ttl = api.storage.posts[-1]
    assert key == f"quarantine/{me['org']['id']}/{body['upload_id']}.pdf"
    assert (max_bytes, ttl) == (50 * 1024 * 1024, 600)
    assert body["fields"]["Content-Type"] == "application/pdf"
    assert body["expires_at"]


async def test_AC1_rejects_oversize_and_non_pdf_before_issuing(api: PapersApi) -> None:
    user = bearer(f"user_{uuid4().hex}")
    too_big = await api.client.post(
        "/api/v1/papers/uploads", json=upload_body(size_bytes=50 * 1024 * 1024 + 1), headers=user
    )
    assert too_big.status_code == 413
    assert too_big.headers["content-type"] == "application/problem+json"
    wrong_type = await api.client.post(
        "/api/v1/papers/uploads", json=upload_body(content_type="text/html"), headers=user
    )
    assert wrong_type.status_code == 422
    bad_hash = await api.client.post(
        "/api/v1/papers/uploads", json=upload_body(sha256="xyz"), headers=user
    )
    assert bad_hash.status_code == 422
    assert not api.storage.posts


async def test_AC1_requires_authentication(api: PapersApi) -> None:
    response = await api.client.post("/api/v1/papers/uploads", json=upload_body())
    assert response.status_code == 401
