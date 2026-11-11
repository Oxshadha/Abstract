"""Vertex AI ranking (Discovery Engine `rank`), Google's own reranker: no new provider (D80).

Called over REST with the existing service account. Errors fall back to the original order, so a
reranker outage never fails a chat answer.
"""

import asyncio
from typing import Any

import httpx

from app.core.logging import get_logger
from app.ports.rerank import Candidate

log = get_logger(__name__)
URL = (
    "https://discoveryengine.googleapis.com/v1/projects/{project}/locations/global/"
    "rankingConfigs/default_ranking_config:rank"
)


class VertexReranker:
    def __init__(
        self,
        project: str,
        model: str,
        *,
        timeout: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
        token: Any = None,
    ) -> None:
        self._url = URL.format(project=project)
        self._model = model
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)
        self._token = token  # tests inject a fixed token; otherwise service-account credentials

    async def _bearer(self) -> str:
        if self._token is not None:
            return str(self._token)
        import google.auth
        import google.auth.transport.requests

        def fetch() -> str:
            creds, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            creds.refresh(google.auth.transport.requests.Request())  # type: ignore[no-untyped-call]
            return str(creds.token)

        return await asyncio.to_thread(fetch)

    async def rerank(self, query: str, candidates: list[Candidate], top_n: int) -> list[str]:
        original = [c.id for c in candidates][:top_n]
        if not candidates:
            return []
        body = {
            "model": self._model,
            "query": query[:1000],
            "topN": top_n,
            "records": [{"id": c.id, "content": c.text[:2000]} for c in candidates],
        }
        try:
            response = await self._client.post(
                self._url, json=body, headers={"Authorization": f"Bearer {await self._bearer()}"}
            )
            response.raise_for_status()
            ranked = [r["id"] for r in response.json().get("records", [])]
        except Exception as exc:
            log.warning("rerank_failed", error=type(exc).__name__)
            return original
        return ranked[:top_n] or original
