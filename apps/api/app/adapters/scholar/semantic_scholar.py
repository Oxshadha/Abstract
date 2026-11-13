"""Semantic Scholar Graph API (spec 014 AC6, AC7; D95), the only outbound HTTP client for it.

allowlist  every request must be https to api.semanticscholar.org (checked per request)
timeout    5 s for connect, read and write
redirects  never followed; a redirect is treated as an error
429        honours Retry-After (capped), a few times, then ScholarBusyError for the job
key        SEMANTIC_SCHOLAR_API_KEY when set (higher rate limit); works without one
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.ports.scholar import (
    ScholarBusyError,
    ScholarPaper,
    ScholarUnavailableError,
)

ALLOWED_HOSTS = frozenset({"api.semanticscholar.org"})
BASE_URL = "https://api.semanticscholar.org/graph/v1"
FIELDS = "title,authors,year,venue,citationCount,url,openAccessPdf"
TIMEOUT_SECONDS = 5.0
BUSY_ATTEMPTS = 3
MAX_RETRY_AFTER = 30.0
MAX_AUTHORS = 20


class DisallowedHostError(Exception):
    """A request to a host outside the allowlist was attempted."""


async def _guard(request: httpx.Request) -> None:
    if request.url.scheme != "https" or request.url.host not in ALLOWED_HOSTS:
        raise DisallowedHostError(request.url.host)


def _paper(data: Any) -> ScholarPaper | None:
    if not isinstance(data, dict) or not data.get("paperId") or not data.get("title"):
        return None
    pdf = data.get("openAccessPdf") or {}
    authors = [a.get("name") for a in data.get("authors") or [] if isinstance(a, dict)]
    return ScholarPaper(
        paper_id=str(data["paperId"]),
        title=str(data["title"])[:500],
        authors=[str(a)[:200] for a in authors if a][:MAX_AUTHORS],
        year=data.get("year") if isinstance(data.get("year"), int) else None,
        venue=(str(data["venue"])[:300] or None) if data.get("venue") else None,
        citations=data.get("citationCount") if isinstance(data.get("citationCount"), int) else None,
        url=str(data.get("url") or f"https://www.semanticscholar.org/paper/{data['paperId']}"),
        pdf_url=str(pdf["url"]) if isinstance(pdf, dict) and pdf.get("url") else None,
    )


class SemanticScholar:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        headers = {"User-Agent": "abstract-research-assistant"}
        if api_key:
            headers["x-api-key"] = api_key
        self._sleep = sleep
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers=headers,
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
            transport=transport,
            event_hooks={"request": [_guard]},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(BUSY_ATTEMPTS):
            try:
                response = await self._client.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                raise ScholarUnavailableError(type(exc).__name__) from exc
            if response.status_code != 429:
                if response.is_redirect:
                    raise ScholarUnavailableError("redirect refused")
                return response
            if attempt + 1 < BUSY_ATTEMPTS:
                await self._sleep(self._retry_after(response, attempt))
        raise ScholarBusyError("rate limited")

    @staticmethod
    def _retry_after(response: httpx.Response, attempt: int) -> float:
        try:
            wait = float(response.headers.get("Retry-After", ""))
        except ValueError:
            wait = 2.0 * (attempt + 1)
        return max(1.0, min(wait, MAX_RETRY_AFTER))

    async def papers_by_ids(self, ids: list[str]) -> list[ScholarPaper | None]:
        if not ids:
            return []
        response = await self._send(
            "POST", "/paper/batch", params={"fields": FIELDS}, json={"ids": ids}
        )
        if response.status_code == 400:  # ids it cannot parse at all: nothing matched
            return [None] * len(ids)
        if response.status_code != 200:
            raise ScholarUnavailableError(f"status {response.status_code}")
        body = response.json()
        if not isinstance(body, list) or len(body) != len(ids):
            raise ScholarUnavailableError("unexpected batch response")
        return [_paper(item) for item in body]

    async def match_title(self, title: str) -> ScholarPaper | None:
        response = await self._send(
            "GET", "/paper/search/match", params={"query": title[:300], "fields": FIELDS}
        )
        if response.status_code in (400, 404):  # no match found
            return None
        if response.status_code != 200:
            raise ScholarUnavailableError(f"status {response.status_code}")
        data = (response.json() or {}).get("data") or []
        return _paper(data[0]) if data else None
