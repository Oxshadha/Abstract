"""Spec 014 AC7: the one outbound HTTP client for Semantic Scholar, with a fake transport."""

import json

import httpx
import pytest

from app.adapters.scholar.semantic_scholar import (
    TIMEOUT_SECONDS,
    DisallowedHostError,
    SemanticScholar,
)
from app.ports.scholar import ScholarBusyError, ScholarUnavailableError

PAPER = {
    "paperId": "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
    "title": "Attention is All you Need",
    "authors": [{"authorId": "1", "name": "Ashish Vaswani"}, {"authorId": "2", "name": "Noam"}],
    "year": 2017,
    "venue": "Neural Information Processing Systems",
    "citationCount": 100000,
    "url": "https://www.semanticscholar.org/paper/204e3073870fae3d05bcbc2f6a8e263d9b72e776",
    "openAccessPdf": {"url": "https://arxiv.org/pdf/1706.03762", "status": "GREEN"},
}


class Recorder:
    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.pop(0)


def client(recorder: Recorder, key: str | None = None) -> tuple[SemanticScholar, list[float]]:
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    return SemanticScholar(key, transport=httpx.MockTransport(recorder), sleep=sleep), slept


async def test_AC7_batch_lookup_by_identifier_parses_public_metadata() -> None:
    recorder = Recorder(httpx.Response(200, json=[PAPER, None]))
    scholar, _ = client(recorder, key="secret")
    found = await scholar.papers_by_ids(["ARXIV:1706.03762", "DOI:10.1/none"])
    request = recorder.requests[0]
    assert request.url.host == "api.semanticscholar.org"
    assert request.url.path == "/graph/v1/paper/batch"
    assert json.loads(request.content) == {"ids": ["ARXIV:1706.03762", "DOI:10.1/none"]}
    assert request.headers["x-api-key"] == "secret"
    assert found[1] is None
    paper = found[0]
    assert paper is not None
    assert (paper.title, paper.year, paper.citations) == ("Attention is All you Need", 2017, 100000)
    assert paper.authors == ["Ashish Vaswani", "Noam"]
    assert paper.pdf_url == "https://arxiv.org/pdf/1706.03762"


async def test_AC7_title_match_and_no_match() -> None:
    recorder = Recorder(
        httpx.Response(200, json={"data": [{**PAPER, "matchScore": 200}]}),
        httpx.Response(404, json={"error": "Title match not found"}),
    )
    scholar, _ = client(recorder)
    assert (await scholar.match_title("Attention is all you need")) is not None
    assert (await scholar.match_title("Nothing like this")) is None
    assert recorder.requests[0].url.params["query"] == "Attention is all you need"
    assert "x-api-key" not in recorder.requests[0].headers  # works without a key


async def test_AC7_only_the_allowlisted_host_and_a_5_second_timeout() -> None:
    recorder = Recorder(httpx.Response(200, json={}))
    scholar, _ = client(recorder)
    assert scholar._client.timeout == httpx.Timeout(TIMEOUT_SECONDS)
    with pytest.raises(DisallowedHostError):
        await scholar._client.get("https://evil.example.com/graph/v1/paper/x")
    with pytest.raises(DisallowedHostError):
        await scholar._client.get("http://api.semanticscholar.org/graph/v1/paper/x")
    assert recorder.requests == []  # refused before anything was sent


async def test_AC7_redirects_are_never_followed() -> None:
    recorder = Recorder(httpx.Response(302, headers={"Location": "https://evil.example.com/"}))
    scholar, _ = client(recorder)
    with pytest.raises(ScholarUnavailableError, match="redirect"):
        await scholar.match_title("Attention")
    assert len(recorder.requests) == 1


async def test_AC7_a_429_backs_off_then_retries() -> None:
    recorder = Recorder(
        httpx.Response(429, headers={"Retry-After": "3"}),
        httpx.Response(200, json={"data": [PAPER]}),
    )
    scholar, slept = client(recorder)
    assert (await scholar.match_title("Attention")) is not None
    assert slept == [3.0]


async def test_AC7_a_service_that_stays_busy_is_handed_to_the_job() -> None:
    recorder = Recorder(*[httpx.Response(429) for _ in range(3)])
    scholar, slept = client(recorder)
    with pytest.raises(ScholarBusyError):
        await scholar.match_title("Attention")
    assert len(slept) == 2


async def test_AC7_network_errors_are_retryable() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    scholar = SemanticScholar(transport=httpx.MockTransport(broken))
    with pytest.raises(ScholarUnavailableError):
        await scholar.papers_by_ids(["DOI:10.1/x"])
