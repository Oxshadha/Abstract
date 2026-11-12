"""Spec 009 AC9: chat answers cite tables and figures and see figure images."""

from collections.abc import AsyncIterator, Iterator
from typing import Any
from uuid import uuid4

import pytest

from app.ports.llm import ImagePart, StreamChunk
from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.test_chat import ScriptedChat, ask, conversation, parse
from tests.integration.test_enrichment import FakeLayout, _enrich, _ingested

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


class SeeingChat(ScriptedChat):
    """Records what the answer model received, including attached images."""

    def __init__(self) -> None:
        super().__init__(answer="The big model reaches 28.4 BLEU [S1].")
        self.answer_messages: list[Any] = []

    async def stream(self, **kwargs: Any) -> AsyncIterator[StreamChunk]:
        self.answer_messages = kwargs["messages"]
        async for chunk in super().stream(**kwargs):
            yield chunk


@pytest.fixture
def seeing(api: PapersApi) -> Iterator[SeeingChat]:
    scripted = SeeingChat()
    real = api.app.state.llm.gateway
    api.app.state.llm.gateway = scripted
    yield scripted
    api.app.state.llm.gateway = real


def _images(messages: list[Any]) -> int:
    return sum(
        isinstance(part, ImagePart)
        for m in messages
        if not isinstance(m.content, str)
        for part in m.content
    )


async def test_AC9_a_named_table_is_cited_with_its_box(
    api: PapersApi, worker: Worker, seeing: SeeingChat
) -> None:
    job, paper, user = await _ingested(api, worker)
    await _enrich(worker, FakeLayout(), job["org_id"])
    cid = await conversation(api, user, paper)
    events = await ask(api, user, cid, "What does Table 1 show?")
    (citations,) = [data["items"] for name, data in events if name == "citations"]
    element = citations[0]["element"]
    assert element["label"] == "Table 1"
    assert element["kind"] == "table"
    assert element["box"] == {"x": 0.1, "y": 0.2, "width": 0.7, "height": 0.1}
    # Reloading the conversation keeps the element (joined through the saved chunk).
    page = (
        await api.client.get(f"/api/v1/conversations/{cid}/messages", headers=bearer(user))
    ).json()
    answer = next(m for m in page["items"] if m["role"] == "assistant")
    assert answer["citations"][0]["element"]["label"] == "Table 1"


async def test_AC9_figure_questions_send_the_figure_image(
    api: PapersApi, worker: Worker, seeing: SeeingChat
) -> None:
    job, paper, user = await _ingested(api, worker)
    await _enrich(worker, FakeLayout(), job["org_id"])
    cid = await conversation(api, user, paper)
    await ask(api, user, cid, "What does Figure 1 show?")
    assert _images(seeing.answer_messages) == 1  # the crop, at most MAX_FIGURE_IMAGES


async def _ask_region(
    api: PapersApi, user: str, cid: str, region: dict[str, Any], question: str = "What is this?"
) -> Any:
    return await api.client.post(
        f"/api/v1/conversations/{cid}/messages",
        json={"content": question, "region": region},
        headers={**bearer(user), "Idempotency-Key": str(uuid4())},
    )


async def test_AC10_AC11_a_region_question_sees_the_crop_and_cites_the_region(
    api: PapersApi, worker: Worker, seeing: SeeingChat
) -> None:
    _job, paper, user = await _ingested(api, worker)
    cid = await conversation(api, user, paper)
    region = {"page": 2, "x": 0.1, "y": 0.2, "width": 0.7, "height": 0.15}
    response = await _ask_region(api, user, cid, region)
    assert response.status_code == 200, response.text
    events = parse(response.text)
    (citations,) = [data["items"] for name, data in events if name == "citations"]
    assert citations[0]["region"] == region  # [S1] is the region
    assert citations[0]["section"] == "Selected region"
    assert _images(seeing.answer_messages) >= 1  # the server-rendered crop
    assert any(task == "region_answer" for task, _ in seeing.calls)
    page = (
        await api.client.get(f"/api/v1/conversations/{cid}/messages", headers=bearer(user))
    ).json()
    question = next(m for m in page["items"] if m["role"] == "user")
    answer = next(m for m in page["items"] if m["role"] == "assistant")
    assert question["region"] == region  # the chip on the question survives a reload
    assert answer["citations"][0]["region"] == region


async def test_AC11_regions_are_bounded(api: PapersApi, worker: Worker, seeing: SeeingChat) -> None:
    _job, paper, user = await _ingested(api, worker)
    cid = await conversation(api, user, paper)
    bad: list[dict[str, Any]] = [
        {"page": 1, "x": 0.1, "y": 0.1, "width": 0.01, "height": 0.2},  # too small
        {"page": 1, "x": 0.8, "y": 0.1, "width": 0.5, "height": 0.2},  # off the page
        {"page": 99, "x": 0.1, "y": 0.1, "width": 0.3, "height": 0.2},  # no such page
        {"page": 1, "x": 0.1, "y": 0.1, "width": 0.3, "height": 0.2, "image": "data:"},  # extra
    ]
    for region in bad:
        response = await _ask_region(api, user, cid, region)
        assert response.status_code == 422, region
