"""Spec 002 AC16 (input validation baseline) and AC17 (never trust client identity)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.ratelimit import MemoryCounterStore
from app.core.schemas import FORBIDDEN_CLIENT_FIELDS, CleanStr, StrictModel, clean_text
from app.factory import create_app
from tests.conftest import make_settings


class Note(StrictModel):
    title: CleanStr
    body: CleanStr = ""


def _app_with_echo() -> Any:
    app = create_app(make_settings(), readiness_checks={}, rate_store=MemoryCounterStore())

    async def echo(note: Note) -> dict[str, str]:
        return note.model_dump()

    app.add_api_route("/echo", echo, methods=["POST"])
    return app


def _client() -> TestClient:
    client = TestClient(_app_with_echo(), raise_server_exceptions=False)
    client.__enter__()
    return client


def test_AC16_unknown_fields_are_rejected() -> None:
    response = _client().post("/echo", json={"title": "x", "role": "admin"})
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_AC16_text_is_normalized_and_control_characters_removed() -> None:
    decomposed = "Café"  # 'e' + combining acute accent
    response = _client().post(
        "/echo", json={"title": f"{decomposed}\x00‮", "body": "line1\nline2\tend\x07"}
    )
    assert response.json() == {"title": "Café", "body": "line1\nline2\tend"}
    assert clean_text("a​b") == "ab"  # zero-width space removed


def test_AC16_oversized_body_is_rejected_before_parsing() -> None:
    client = _client()
    big = {"title": "x", "body": "a" * 1_100_000}
    response = client.post("/echo", json=big)
    assert response.status_code == 413
    assert response.headers["content-type"] == "application/problem+json"


def test_AC16_chunked_body_without_length_is_still_limited() -> None:
    client = _client()

    def chunks() -> Any:
        yield b'{"title": "x", "body": "'
        for _ in range(120):
            yield b"a" * 10_000
        yield b'"}'

    response = client.post("/echo", content=chunks(), headers={"content-type": "application/json"})
    assert response.status_code == 413


def test_AC16_strings_are_bounded() -> None:
    response = _client().post("/echo", json={"title": "a" * 10_001})
    assert response.status_code == 422


def _request_schema_names(openapi: dict[str, Any]) -> set[str]:
    names = set()
    for path in openapi.get("paths", {}).values():
        for op in path.values():
            content = op.get("requestBody", {}).get("content", {})
            for media in content.values():
                ref = media.get("schema", {}).get("$ref", "")
                if ref:
                    names.add(ref.rsplit("/", 1)[-1])
    return names


def _all_request_fields(openapi: dict[str, Any]) -> set[str]:
    schemas = openapi.get("components", {}).get("schemas", {})
    fields: set[str] = set()
    for name in _request_schema_names(openapi):
        fields.update(schemas.get(name, {}).get("properties", {}))
    for path in openapi.get("paths", {}).values():
        for op in path.values():
            fields.update(p["name"] for p in op.get("parameters", []) if p.get("in") == "query")
    return fields


def test_AC16_every_request_body_schema_is_strict() -> None:
    app = create_app(make_settings(), readiness_checks={}, rate_store=MemoryCounterStore())
    openapi = app.openapi()
    schemas = openapi.get("components", {}).get("schemas", {})
    lax = [
        n
        for n in _request_schema_names(openapi)
        if schemas[n].get("additionalProperties") is not False
    ]
    assert not lax, f"request schemas accepting unknown fields: {lax}"


def test_AC17_no_request_accepts_identity_or_ownership_fields() -> None:
    app = create_app(make_settings(), readiness_checks={}, rate_store=MemoryCounterStore())
    offending = _all_request_fields(app.openapi()) & FORBIDDEN_CLIENT_FIELDS
    assert not offending, f"client-supplied identity/ownership fields: {offending}"


def test_AC17_scan_catches_a_tampering_field() -> None:
    class Bad(StrictModel):
        title: str
        org_id: str

    app = create_app(make_settings(), readiness_checks={}, rate_store=MemoryCounterStore())

    async def bad(payload: Bad) -> None:
        return None

    app.add_api_route("/bad", bad, methods=["POST"])
    assert _all_request_fields(app.openapi()) & FORBIDDEN_CLIENT_FIELDS == {"org_id"}


@pytest.mark.parametrize("field", sorted(FORBIDDEN_CLIENT_FIELDS))
def test_AC17_forbidden_list_covers_core_identity_fields(field: str) -> None:
    assert field.islower()
