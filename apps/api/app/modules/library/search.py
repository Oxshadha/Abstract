"""Search across the caller's papers (spec 013 AC8): Postgres full text and trigram matching
only, so a search costs no model tokens. Two statements whatever the result size (AC9)."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.library.schemas import PaperHit, PassageHit, SearchResults

PAPER_LIMIT = 8
PASSAGE_LIMIT = 10
_HEADLINE = "StartSel=«, StopSel=», MaxWords=28, MinWords=12, MaxFragments=1, FragmentDelimiter= … "


def _like(query: str) -> str:
    escaped = query.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def search(
    session: AsyncSession, owner_id: UUID, query: str, collection_id: UUID | None
) -> SearchResults:
    params: dict[str, object] = {
        "o": owner_id,
        "q": query,
        "like": _like(query),
        "headline": _HEADLINE,
    }
    scope = ""
    if collection_id is not None:
        scope = (
            " AND EXISTS (SELECT 1 FROM collection_papers cp WHERE cp.paper_id = p.id"
            " AND cp.collection_id = :collection)"
        )
        params["collection"] = collection_id
    # Word-level typo tolerance ("quantom" finds "Quantum error correction"); transaction-local.
    await session.execute(text("SET LOCAL pg_trgm.word_similarity_threshold = 0.4"))
    papers = (
        await session.execute(
            text(
                "SELECT p.id, coalesce(p.title, p.filename) AS title, p.authors, p.year,"  # noqa: S608 (constant clauses; input is bound)
                " ts_rank(p.search, websearch_to_tsquery('simple', :q))"
                " + word_similarity(lower(:q), lower(coalesce(p.title, p.filename))) AS score"
                " FROM papers p WHERE p.owner_id = :o"
                " AND (p.search @@ websearch_to_tsquery('simple', :q)"
                " OR lower(coalesce(p.title, p.filename)) LIKE :like"
                " OR lower(:q) <% lower(coalesce(p.title, p.filename)))"
                f"{scope} ORDER BY score DESC, p.created_at DESC LIMIT {PAPER_LIMIT}"
            ),
            params,
        )
    ).all()
    passages = (
        await session.execute(
            text(
                "WITH hits AS ("  # noqa: S608 (constant clauses; input is bound)
                " SELECT c.paper_id, c.page_start, c.text,"
                " ts_rank_cd(c.tsv, websearch_to_tsquery('english', :q)) AS score"
                " FROM chunks c JOIN papers p ON p.id = c.paper_id"
                " WHERE p.owner_id = :o AND c.tsv @@ websearch_to_tsquery('english', :q)"
                f"{scope} ORDER BY score DESC LIMIT {PASSAGE_LIMIT})"
                " SELECT h.paper_id, coalesce(p.title, p.filename) AS paper_title,"
                " h.page_start AS page,"
                " ts_headline('english', h.text, websearch_to_tsquery('english', :q), :headline)"
                " AS snippet FROM hits h JOIN papers p ON p.id = h.paper_id ORDER BY h.score DESC"
            ),
            params,
        )
    ).all()
    return SearchResults(
        papers=[
            PaperHit(id=r.id, title=r.title, authors=list(r.authors or []), year=r.year)
            for r in papers
        ],
        passages=[
            PassageHit(
                paper_id=r.paper_id, paper_title=r.paper_title, page=r.page, snippet=r.snippet
            )
            for r in passages
        ],
    )
