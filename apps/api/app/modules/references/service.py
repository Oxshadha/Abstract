"""The paper's references (spec 014 AC5, AC6): stored at ingest, matched in the background.

store_extracted  (store.py) called by ingest with the page texts.
run_matching     the background job: identifiers first (one batch request), then titles one
                 at a time at most once per `scholar_interval_seconds`, every answer cached in
                 scholar_cache. Progress is saved as it goes, so a retry resumes; after
                 BUDGET_SECONDS the job hands the rest to a fresh job instead of hogging the
                 background worker. Matching never touches the paper's status (never blocks).
give_up          retries ran out: what is left stays raw (unmatched).
listing          the API view.
"""

import asyncio
import contextlib
import json
import re
import time
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.core.tenancy import set_tenant
from app.modules.papers.ingest import Deps
from app.modules.papers.jobs import InvalidTransitionError, transition
from app.modules.references.store import MATCH_TASK, create_job
from app.ports.scholar import ScholarPaper

BUDGET_SECONDS = 120.0
BATCH_SIZE = 100
TITLE_COVERAGE = 0.8  # share of the matched title's words that must appear in the raw entry
log = get_logger(__name__)


# ---------- matching (AC6, AC7) ----------


def _words(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def title_key(title: str) -> str:
    return "title:" + " ".join(_words(title))[:390]


def id_key(doi: str | None, arxiv_id: str | None) -> str | None:
    if doi:
        return f"doi:{doi.lower()}"[:400]
    if arxiv_id:
        return f"arxiv:{arxiv_id}"
    return None


def _api_id(key: str) -> str:
    kind, value = key.split(":", 1)
    return f"{'DOI' if kind == 'doi' else 'ARXIV'}:{value}"


def plausible(raw: str, paper: ScholarPaper) -> bool:
    """A title match is kept only when the matched title's words are in the entry itself."""
    words = _words(paper.title)
    if not words:
        return False
    present = set(_words(raw))
    return sum(w in present for w in words) / len(words) >= TITLE_COVERAGE


async def _cached(session: AsyncSession, keys: list[str]) -> dict[str, dict[str, Any] | None]:
    if not keys:
        return {}
    rows = await session.execute(
        text("SELECT key, data FROM scholar_cache WHERE key = ANY(:k) AND expires_at > now()"),
        {"k": keys},
    )
    return {r.key: r.data for r in rows}


async def _remember(session: AsyncSession, key: str, paper: ScholarPaper | None) -> None:
    await session.execute(
        text(
            "INSERT INTO scholar_cache (key, data) VALUES (:k, CAST(:d AS jsonb))"
            " ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data, fetched_at = now(),"
            " expires_at = now() + interval '30 days'"
        ),
        {"k": key, "d": json.dumps(paper.model_dump()) if paper else None},
    )


async def _settle(
    session: AsyncSession, paper_id: UUID, n: int, paper: dict[str, Any] | None
) -> None:
    await session.execute(
        text(
            "UPDATE paper_references SET status = :s, match = CAST(:m AS jsonb)"
            " WHERE paper_id = :p AND n = :n AND status = 'pending'"
        ),
        {
            "s": "matched" if paper else "unmatched",
            "m": json.dumps(paper) if paper else None,
            "p": paper_id,
            "n": n,
        },
    )


async def run_matching(deps: Deps, org_id: UUID, job_id: UUID) -> None:
    maker = deps.sessionmaker
    async with maker() as session, session.begin():
        await set_tenant(session, org_id)
        paper_id = (
            await session.execute(text("SELECT paper_id FROM jobs WHERE id = :j"), {"j": job_id})
        ).scalar_one()
        pending = (
            await session.execute(
                text(
                    "SELECT n, raw, doi, arxiv_id, title_query FROM paper_references"
                    " WHERE paper_id = :p AND status = 'pending' ORDER BY n"
                ),
                {"p": paper_id},
            )
        ).all()
    client = deps.scholar
    if client is None or not pending:  # no client configured: entries stay raw
        async with maker() as session, session.begin():
            await set_tenant(session, org_id)
            for ref in pending:
                await _settle(session, paper_id, ref.n, None)
        return

    started = time.monotonic()
    interval = deps.settings.scholar_interval_seconds
    keys = {ref.n: id_key(ref.doi, ref.arxiv_id) for ref in pending}

    # 1. Identifiers: everything not cached, in batches.
    async with maker() as session, session.begin():
        cache = await _cached(session, [k for k in keys.values() if k])
    missing = sorted({k for k in keys.values() if k and k not in cache})
    for i in range(0, len(missing), BATCH_SIZE):
        batch = missing[i : i + BATCH_SIZE]
        found = await client.papers_by_ids([_api_id(k) for k in batch])
        async with maker() as session, session.begin():
            for key, paper in zip(batch, found, strict=True):
                await _remember(session, key, paper)
                cache[key] = paper.model_dump() if paper else None
        await asyncio.sleep(interval)

    # 2. Settle what the identifiers matched; the rest go by title.
    by_title: list[Any] = []
    async with maker() as session, session.begin():
        await set_tenant(session, org_id)
        for ref in pending:
            known = keys[ref.n]
            if known and cache.get(known):
                await _settle(session, paper_id, ref.n, cache[known])
            elif ref.title_query:
                by_title.append(ref)
            else:
                await _settle(session, paper_id, ref.n, None)
        titles = await _cached(session, [title_key(r.title_query) for r in by_title])

    for ref in by_title:
        key = title_key(ref.title_query)
        if key not in titles:
            if time.monotonic() - started > BUDGET_SECONDS:
                await _continue(deps, org_id, paper_id)
                return
            paper = await client.match_title(ref.title_query)
            titles[key] = paper.model_dump() if paper else None
            async with maker() as session, session.begin():
                await _remember(session, key, paper)
            await asyncio.sleep(interval)
        data = titles[key]
        keep = data if data and plausible(ref.raw, ScholarPaper.model_validate(data)) else None
        async with maker() as session, session.begin():
            await set_tenant(session, org_id)
            await _settle(session, paper_id, ref.n, keep)
    log.info("references_matched", paper_id=str(paper_id), entries=len(pending))


async def _continue(deps: Deps, org_id: UUID, paper_id: UUID) -> None:
    """Out of time for this run: a fresh job picks up the entries still pending."""
    async with deps.sessionmaker() as session, session.begin():
        await set_tenant(session, org_id)
        job = await create_job(session, org_id, paper_id)
    try:
        deps.enqueue(MATCH_TASK, {"job_id": str(job), "org_id": str(org_id)})
    except Exception as exc:
        log.error("enqueue_failed", job_id=str(job), error=type(exc).__name__)
        await give_up(deps, org_id, job, "enqueue failed")


async def give_up(deps: Deps, org_id: UUID, job_id: UUID, reason: str) -> None:
    """Retries ran out: the job fails, the entries left keep their raw text, the paper is fine."""
    async with deps.sessionmaker() as session, session.begin():
        await set_tenant(session, org_id)
        with contextlib.suppress(InvalidTransitionError):
            await transition(session, job_id, "failed", error=reason[:500])
        await session.execute(
            text(
                "UPDATE paper_references SET status = 'unmatched' WHERE status = 'pending'"
                " AND paper_id = (SELECT paper_id FROM jobs WHERE id = :j)"
            ),
            {"j": job_id},
        )


# ---------- the API view ----------


class ReferenceMatch(BaseModel):
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    citations: int | None
    url: str
    pdf_url: str | None


class ReferenceItem(BaseModel):
    n: int
    label: str | None
    raw: str
    match: ReferenceMatch | None


class References(BaseModel):
    # pending: the paper is still being read; matching: lookups running; none: no list found
    status: Literal["pending", "matching", "done", "none"]
    items: list[ReferenceItem]


async def listing(session: AsyncSession, owner_id: UUID, paper_id: UUID) -> References:
    paper = (
        await session.execute(
            text("SELECT text_status FROM papers WHERE id = :p AND owner_id = :o"),
            {"p": paper_id, "o": owner_id},
        )
    ).first()
    if paper is None:
        raise ProblemError(404, "paper-not-found", "This paper was not found.")
    rows = (
        await session.execute(
            text(
                "SELECT n, label, raw, status, match FROM paper_references WHERE paper_id = :p"
                " ORDER BY n"
            ),
            {"p": paper_id},
        )
    ).all()
    items = [
        ReferenceItem(
            n=r.n,
            label=r.label,
            raw=r.raw,
            match=ReferenceMatch.model_validate(r.match) if r.match else None,
        )
        for r in rows
    ]
    if not rows:
        status: Literal["pending", "matching", "done", "none"] = (
            "pending" if paper.text_status == "pending" else "none"
        )
    else:
        status = "matching" if any(r.status == "pending" for r in rows) else "done"
    return References(status=status, items=items)
