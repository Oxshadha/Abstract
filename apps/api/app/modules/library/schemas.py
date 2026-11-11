from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, StringConstraints

from app.core.schemas import CleanStr, StrictModel

CollectionName = Annotated[CleanStr, StringConstraints(min_length=1, max_length=60)]


class CollectionIn(StrictModel):
    name: CollectionName


class CollectionOut(BaseModel):
    id: UUID
    name: str
    paper_count: int


class CollectionList(BaseModel):
    items: list[CollectionOut]


class PaperHit(BaseModel):
    id: UUID
    title: str
    authors: list[str]
    year: int | None


class PassageHit(BaseModel):
    paper_id: UUID
    paper_title: str
    page: int
    snippet: str  # plain text; matched words are wrapped in « » for the client to emphasise


class SearchResults(BaseModel):
    papers: list[PaperHit]
    passages: list[PassageHit]
