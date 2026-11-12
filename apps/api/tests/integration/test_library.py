"""Spec 013: Library list, star, collections and search on real Postgres (runtime role)."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import event, text

from tests.fakes.auth import bearer
from tests.fakes.pdfs import make_pdf
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import PAGE, new_user, upload_pdf

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


async def _paper(api: PapersApi, user: str, title: str) -> str:
    response = await upload_pdf(api, user, make_pdf([[title, f"Body of {title}."]]))
    paper_id: str = response.json()["paper"]["id"]
    # Titles normally come from ingestion; set them directly (rename) for these list tests.
    renamed = await api.client.patch(
        f"/api/v1/papers/{paper_id}", json={"title": title}, headers=bearer(user)
    )
    assert renamed.status_code == 200, renamed.text
    return paper_id


async def _set(worker: Worker, paper_id: str, **columns: Any) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in columns)
    async with worker.admin.begin() as conn:
        sql = f"UPDATE papers SET {sets} WHERE id = :id"  # noqa: S608 (column names from the test)
        await conn.execute(text(sql), {**columns, "id": paper_id})


async def _ids(api: PapersApi, user: str, **params: Any) -> list[str]:
    seen: list[str] = []
    cursor = None
    while True:
        query = {"limit": 2, **params, **({"cursor": cursor} if cursor else {})}
        response = await api.client.get("/api/v1/papers", params=query, headers=bearer(user))
        assert response.status_code == 200, response.text
        page = response.json()
        seen += [p["id"] for p in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            return seen


async def test_AC3_AC11_sorts_page_with_stable_cursors(api: PapersApi, worker: Worker) -> None:
    user = new_user()
    b = await _paper(api, user, "Beta networks")
    a = await _paper(api, user, "alpha models")
    c = await _paper(api, user, "Gamma rays")
    assert await _ids(api, user) == [c, a, b]  # Recently added (default)
    assert await _ids(api, user, sort="title") == [a, b, c]  # case-insensitive A to Z
    opened = await api.client.post(f"/api/v1/papers/{b}/opened", headers=bearer(user))
    assert opened.status_code == 204
    assert (await _ids(api, user, sort="opened"))[0] == b
    # A cursor from one sort is rejected by another.
    first = await api.client.get("/api/v1/papers", params={"limit": 1}, headers=bearer(user))
    cursor = first.json()["next_cursor"]
    wrong = await api.client.get(
        "/api/v1/papers", params={"sort": "title", "cursor": cursor}, headers=bearer(user)
    )
    assert wrong.status_code == 400


async def test_AC3_AC5_filters_by_type_and_star(api: PapersApi, worker: Worker) -> None:
    user = new_user()
    report = await _paper(api, user, "Annual report")
    paper = await _paper(api, user, "A study")
    await _set(worker, report, doc_type="report")
    await _set(worker, paper, doc_type="paper")
    assert await _ids(api, user, type="report") == [report]
    starred = await api.client.patch(
        f"/api/v1/papers/{paper}", json={"starred": True}, headers=bearer(user)
    )
    assert starred.status_code == 200
    assert starred.json()["starred"] is True
    assert await _ids(api, user, starred="true") == [paper]


async def test_AC5_rename_sticks_and_other_users_cannot_edit(
    api: PapersApi, worker: Worker
) -> None:
    user, intruder = new_user(), new_user()
    paper = await _paper(api, user, "Old title")
    renamed = await api.client.patch(
        f"/api/v1/papers/{paper}", json={"title": "My name for it"}, headers=bearer(user)
    )
    assert renamed.json()["title"] == "My name for it"
    row = await worker.row("SELECT title_edited FROM papers WHERE id = :id", id=paper)
    assert row.title_edited is True  # the summary will not overwrite it
    for body in ({"starred": True}, {"title": "x"}):
        response = await api.client.patch(
            f"/api/v1/papers/{paper}", json=body, headers=bearer(intruder)
        )
        assert response.status_code == 404
    empty = await api.client.patch(f"/api/v1/papers/{paper}", json={}, headers=bearer(user))
    assert empty.status_code == 422
    unknown = await api.client.patch(
        f"/api/v1/papers/{paper}", json={"owner_id": "x"}, headers=bearer(user)
    )
    assert unknown.status_code == 422


async def test_AC6_AC7_collections_filter_the_library(api: PapersApi) -> None:
    user = new_user()
    headers = bearer(user)
    one = await _paper(api, user, "First paper")
    two = await _paper(api, user, "Second paper")
    created = await api.client.post("/api/v1/collections", json={"name": "RAG"}, headers=headers)
    assert created.status_code == 201
    rag = created.json()["id"]
    duplicate = await api.client.post("/api/v1/collections", json={"name": "rag"}, headers=headers)
    assert duplicate.status_code == 409
    for _ in range(2):  # idempotent
        added = await api.client.put(f"/api/v1/collections/{rag}/papers/{one}", headers=headers)
        assert added.status_code == 204
    listed = (await api.client.get("/api/v1/collections", headers=headers)).json()["items"]
    assert listed == [{"id": rag, "name": "RAG", "paper_count": 1}]
    assert await _ids(api, user, collection=rag) == [one]
    assert (await api.client.get(f"/api/v1/papers/{one}/collections", headers=headers)).json() == [
        rag
    ]
    renamed = await api.client.patch(
        f"/api/v1/collections/{rag}", json={"name": "RAG & LLMs"}, headers=headers
    )
    assert renamed.json() == {"id": rag, "name": "RAG & LLMs", "paper_count": 1}
    removed = await api.client.delete(f"/api/v1/collections/{rag}/papers/{one}", headers=headers)
    assert removed.status_code == 204
    assert await _ids(api, user, collection=rag) == []
    await api.client.put(f"/api/v1/collections/{rag}/papers/{two}", headers=headers)
    deleted = await api.client.delete(f"/api/v1/collections/{rag}", headers=headers)
    assert deleted.status_code == 204
    assert sorted(await _ids(api, user)) == sorted([one, two])  # papers survive (AC6)


async def test_AC6_collections_are_private(api: PapersApi) -> None:
    owner, intruder = new_user(), new_user()
    paper = await _paper(api, owner, "Owner paper")
    mine = (
        await api.client.post("/api/v1/collections", json={"name": "Mine"}, headers=bearer(owner))
    ).json()["id"]
    theirs = (
        await api.client.post(
            "/api/v1/collections", json={"name": "Theirs"}, headers=bearer(intruder)
        )
    ).json()["id"]
    intruder_headers = bearer(intruder)
    assert (
        await api.client.get(
            "/api/v1/papers", params={"collection": mine}, headers=intruder_headers
        )
    ).status_code == 404
    assert (
        await api.client.delete(f"/api/v1/collections/{mine}", headers=intruder_headers)
    ).status_code == 404
    # Neither someone else's paper into my collection nor my paper into theirs.
    assert (
        await api.client.put(
            f"/api/v1/collections/{theirs}/papers/{paper}", headers=intruder_headers
        )
    ).status_code == 404
    assert (
        await api.client.put(f"/api/v1/collections/{mine}/papers/{paper}", headers=intruder_headers)
    ).status_code == 404
    assert (await api.client.get("/api/v1/collections", headers=intruder_headers)).json()["items"][
        0
    ]["name"] == "Theirs"


async def test_AC8_search_finds_titles_typos_authors_and_passages(
    api: PapersApi, worker: Worker
) -> None:
    user, other = new_user(), new_user()
    body = (await upload_pdf(api, user, make_pdf([PAGE]))).json()
    indexed = body["paper"]["id"]
    job = api.enqueued[-1][1]
    await worker.run(job["org_id"], job["job_id"])  # indexes the text so passages exist
    plain = await _paper(api, user, "Quantum error correction")
    await _set(worker, plain, authors='["Ada Lovelace"]')
    await _paper(api, other, "Quantum secrets of another user")
    headers = bearer(user)

    async def search(q: str, **params: Any) -> dict[str, Any]:
        response = await api.client.get(
            "/api/v1/search", params={"q": q, **params}, headers=headers
        )
        assert response.status_code == 200, response.text
        result: dict[str, Any] = response.json()
        return result

    assert [p["id"] for p in (await search("quantum"))["papers"]] == [plain]  # not the other user's
    assert [p["id"] for p in (await search("quantom"))["papers"]] == [plain]  # typo (trigram)
    assert [p["id"] for p in (await search("lovelace"))["papers"]] == [plain]  # author
    passages = (await search("relates positions"))["passages"]
    assert passages
    assert passages[0]["paper_id"] == indexed
    assert passages[0]["page"] == 1
    assert "«" in passages[0]["snippet"]
    rag = (
        await api.client.post("/api/v1/collections", json={"name": "Physics"}, headers=headers)
    ).json()["id"]
    assert (await search("quantum", collection=rag))["papers"] == []  # scoped to the collection
    for q in ("a", "x" * 201):
        assert (
            await api.client.get("/api/v1/search", params={"q": q}, headers=headers)
        ).status_code == 422


@contextmanager
def _count_statements(api: PapersApi) -> Iterator[list[str]]:
    statements: list[str] = []
    engine = api.app.state.engine.sync_engine

    def listen(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        if any(
            t in statement for t in ("FROM papers", "FROM collections", "FROM chunks", "WITH hits")
        ):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", listen)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", listen)


async def test_AC9_query_budget_does_not_grow_with_page_size(api: PapersApi) -> None:
    user = new_user()
    headers = bearer(user)
    rag = (
        await api.client.post("/api/v1/collections", json={"name": "All"}, headers=headers)
    ).json()["id"]
    for n in range(6):
        paper = await _paper(api, user, f"Budget paper {n}")
        await api.client.put(f"/api/v1/collections/{rag}/papers/{paper}", headers=headers)
    requests: list[tuple[str, dict[str, Any]]] = [
        ("/api/v1/papers", {"limit": 50}),
        ("/api/v1/papers", {"limit": 50, "collection": rag, "sort": "title"}),
        ("/api/v1/collections", {}),
        ("/api/v1/search", {"q": "budget paper"}),
    ]
    for path, params in requests:
        with _count_statements(api) as statements:
            response = await api.client.get(path, params=params, headers=headers)
        assert response.status_code == 200, (path, response.text)
        assert len(statements) <= 3, (path, statements)


async def test_AC14_list_and_search_use_their_indexes(worker: Worker) -> None:
    async with worker.admin.begin() as conn:
        await conn.execute(text("SET LOCAL enable_seqscan = off"))
        mine = "org_id = '00000000-0000-0000-0000-000000000001' AND owner_id = '00000000-0000-0000-0000-000000000002'"  # noqa: E501
        plans = {
            "papers_org_owner_created_idx": (
                f"SELECT id FROM papers WHERE {mine} ORDER BY created_at DESC, id DESC LIMIT 20"  # noqa: S608
            ),
            "papers_owner_title_idx": (
                f"SELECT id FROM papers WHERE {mine}"  # noqa: S608
                " ORDER BY lower(coalesce(title, filename)), id LIMIT 20"
            ),
            "papers_search_idx": (
                "SELECT id FROM papers WHERE search @@ websearch_to_tsquery('simple', 'quantum')"
            ),
            "papers_title_trgm_idx": (
                "SELECT id FROM papers WHERE 'quantom' <% lower(coalesce(title, filename))"
            ),
        }
        for index, sql in plans.items():
            plan = "\n".join(r[0] for r in (await conn.execute(text(f"EXPLAIN {sql}"))).all())
            assert index in plan, (index, plan)
