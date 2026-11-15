"""Collections (spec 013 AC6, AC7): folders over the Library. Owner-scoped on top of RLS."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemError
from app.modules.library.schemas import CollectionList, CollectionOut

_DUPLICATE = ("duplicate-name", "You already have a collection with this name.")


def _not_found() -> ProblemError:
    return ProblemError(404, "collection-not-found", "This collection was not found.")


async def owned(session: AsyncSession, owner_id: UUID, collection_id: UUID) -> None:
    found = (
        await session.execute(
            text("SELECT 1 FROM collections WHERE id = :c AND owner_id = :o"),
            {"c": collection_id, "o": owner_id},
        )
    ).first()
    if found is None:
        raise _not_found()


_COUNTED = (
    "SELECT c.id, c.name, (SELECT count(*) FROM collection_papers cp"
    " WHERE cp.collection_id = c.id) AS paper_count FROM collections c"
)


async def list_collections(session: AsyncSession, owner_id: UUID) -> CollectionList:
    rows = (
        await session.execute(
            text(f"{_COUNTED} WHERE c.owner_id = :o ORDER BY lower(c.name)"), {"o": owner_id}
        )
    ).all()
    return CollectionList(items=[CollectionOut.model_validate(r._asdict()) for r in rows])


async def _one(session: AsyncSession, owner_id: UUID, collection_id: UUID) -> CollectionOut:
    row = (
        await session.execute(
            text(f"{_COUNTED} WHERE c.id = :c AND c.owner_id = :o"),
            {"c": collection_id, "o": owner_id},
        )
    ).first()
    if row is None:
        raise _not_found()
    return CollectionOut.model_validate(row._asdict())


async def create(session: AsyncSession, org_id: UUID, owner_id: UUID, name: str) -> CollectionOut:
    try:
        async with session.begin_nested():
            new_id = (
                await session.execute(
                    text(
                        "INSERT INTO collections (org_id, owner_id, name)"
                        " VALUES (:org, :o, :n) RETURNING id"
                    ),
                    {"org": org_id, "o": owner_id, "n": name},
                )
            ).scalar_one()
    except IntegrityError as exc:
        raise ProblemError(409, *_DUPLICATE) from exc
    return CollectionOut(id=new_id, name=name, paper_count=0)


async def rename(
    session: AsyncSession, owner_id: UUID, collection_id: UUID, name: str
) -> CollectionOut:
    try:
        async with session.begin_nested():
            result = await session.execute(
                text(
                    "UPDATE collections SET name = :n, updated_at = now()"
                    " WHERE id = :c AND owner_id = :o"
                ),
                {"n": name, "c": collection_id, "o": owner_id},
            )
    except IntegrityError as exc:
        raise ProblemError(409, *_DUPLICATE) from exc
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise _not_found()
    return await _one(session, owner_id, collection_id)


async def delete(session: AsyncSession, owner_id: UUID, collection_id: UUID) -> None:
    """Deletes the folder only; its papers stay in the Library (AC6)."""
    result = await session.execute(
        text("DELETE FROM collections WHERE id = :c AND owner_id = :o"),
        {"c": collection_id, "o": owner_id},
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise _not_found()


async def add_paper(
    session: AsyncSession, org_id: UUID, owner_id: UUID, collection_id: UUID, paper_id: UUID
) -> None:
    """Idempotent; both the collection and the paper must belong to the caller."""
    result = await session.execute(
        text(
            "INSERT INTO collection_papers (collection_id, paper_id, org_id)"
            " SELECT c.id, p.id, :org FROM collections c, papers p"
            " WHERE c.id = :c AND c.owner_id = :o AND p.id = :p AND p.owner_id = :o"
            " ON CONFLICT DO NOTHING RETURNING 1"
        ),
        {"org": org_id, "c": collection_id, "p": paper_id, "o": owner_id},
    )
    if result.first() is None:
        await _check_both(session, owner_id, collection_id, paper_id)


async def remove_paper(
    session: AsyncSession, owner_id: UUID, collection_id: UUID, paper_id: UUID
) -> None:
    await _check_both(session, owner_id, collection_id, paper_id)
    await session.execute(
        text("DELETE FROM collection_papers WHERE collection_id = :c AND paper_id = :p"),
        {"c": collection_id, "p": paper_id},
    )


async def _check_both(
    session: AsyncSession, owner_id: UUID, collection_id: UUID, paper_id: UUID
) -> None:
    row = (
        await session.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM collections WHERE id = :c AND owner_id = :o) AS c,"
                " EXISTS (SELECT 1 FROM papers WHERE id = :p AND owner_id = :o"
                " AND deleted_at IS NULL) AS p"
            ),
            {"c": collection_id, "p": paper_id, "o": owner_id},
        )
    ).one()
    if not row.c:
        raise _not_found()
    if not row.p:
        raise ProblemError(404, "paper-not-found", "This paper was not found.")


async def for_paper(session: AsyncSession, owner_id: UUID, paper_id: UUID) -> list[UUID]:
    rows = await session.execute(
        text(
            "SELECT cp.collection_id FROM collection_papers cp JOIN collections c"
            " ON c.id = cp.collection_id WHERE cp.paper_id = :p AND c.owner_id = :o"
        ),
        {"p": paper_id, "o": owner_id},
    )
    return list(rows.scalars().all())
