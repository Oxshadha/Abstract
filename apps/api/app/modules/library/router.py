from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.core.context import Context
from app.core.policy import require
from app.core.ratelimit import user_rate_limit
from app.modules.library import collections, search
from app.modules.library.schemas import CollectionIn, CollectionList, CollectionOut, SearchResults

router = APIRouter(tags=["library"])


@router.get(
    "/collections",
    response_model=CollectionList,
    summary="The caller's collections with paper counts, by name",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def list_collections(
    ctx: Annotated[Context, Depends(require("collection.read"))],
) -> CollectionList:
    return await collections.list_collections(ctx.session, ctx.identity.user_id)


@router.post(
    "/collections",
    status_code=201,
    response_model=CollectionOut,
    summary="Create a collection",
    responses={409: {"description": "A collection with this name exists"}},
    dependencies=[Depends(user_rate_limit("write"))],
)
async def create_collection(
    body: CollectionIn, ctx: Annotated[Context, Depends(require("collection.create"))]
) -> CollectionOut:
    return await collections.create(
        ctx.session, ctx.identity.org_id, ctx.identity.user_id, body.name
    )


@router.patch(
    "/collections/{collection_id}",
    response_model=CollectionOut,
    summary="Rename a collection",
    responses={409: {"description": "A collection with this name exists"}},
    dependencies=[Depends(user_rate_limit("write"))],
)
async def rename_collection(
    collection_id: UUID,
    body: CollectionIn,
    ctx: Annotated[Context, Depends(require("collection.update"))],
) -> CollectionOut:
    return await collections.rename(ctx.session, ctx.identity.user_id, collection_id, body.name)


@router.delete(
    "/collections/{collection_id}",
    status_code=204,
    summary="Delete a collection (its papers stay in the Library)",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def delete_collection(
    collection_id: UUID, ctx: Annotated[Context, Depends(require("collection.delete"))]
) -> Response:
    await collections.delete(ctx.session, ctx.identity.user_id, collection_id)
    return Response(status_code=204)


@router.put(
    "/collections/{collection_id}/papers/{paper_id}",
    status_code=204,
    summary="Add a paper to a collection (idempotent)",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def add_paper(
    collection_id: UUID,
    paper_id: UUID,
    ctx: Annotated[Context, Depends(require("collection.update"))],
) -> Response:
    await collections.add_paper(
        ctx.session, ctx.identity.org_id, ctx.identity.user_id, collection_id, paper_id
    )
    return Response(status_code=204)


@router.delete(
    "/collections/{collection_id}/papers/{paper_id}",
    status_code=204,
    summary="Remove a paper from a collection (the paper stays in the Library)",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def remove_paper(
    collection_id: UUID,
    paper_id: UUID,
    ctx: Annotated[Context, Depends(require("collection.update"))],
) -> Response:
    await collections.remove_paper(ctx.session, ctx.identity.user_id, collection_id, paper_id)
    return Response(status_code=204)


@router.get(
    "/papers/{paper_id}/collections",
    response_model=list[UUID],
    summary="The collections a paper is in (for the Add to collection menu)",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def paper_collections(
    paper_id: UUID, ctx: Annotated[Context, Depends(require("collection.read"))]
) -> list[UUID]:
    return await collections.for_paper(ctx.session, ctx.identity.user_id, paper_id)


@router.get(
    "/search",
    response_model=SearchResults,
    summary="Search the caller's papers by title, author and text (no model calls)",
    dependencies=[Depends(user_rate_limit("search"))],
)
async def search_papers(
    ctx: Annotated[Context, Depends(require("search.read"))],
    q: Annotated[str, Query(min_length=2, max_length=200)],
    collection: UUID | None = None,
) -> SearchResults:
    if collection is not None:
        await collections.owned(ctx.session, ctx.identity.user_id, collection)
    return await search.search(ctx.session, ctx.identity.user_id, q.strip(), collection)
