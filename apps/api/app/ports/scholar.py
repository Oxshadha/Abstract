"""Scholarly metadata port (spec 014 AC6, AC7): look papers up by identifier or by title.

Only public metadata crosses this port; nothing about the user or their paper is sent except
the identifiers and titles from the paper's own reference list.
"""

from typing import Protocol

from pydantic import BaseModel


class ScholarPaper(BaseModel):
    paper_id: str
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    citations: int | None
    url: str
    pdf_url: str | None


class ScholarBusyError(Exception):
    """The service kept answering 429 (rate limited); the job backs off and retries."""


class ScholarUnavailableError(Exception):
    """The service could not be reached or answered with an error (retried)."""


class ScholarClient(Protocol):
    async def papers_by_ids(self, ids: list[str]) -> list[ScholarPaper | None]:
        """Papers for "DOI:..." / "ARXIV:..." ids, aligned with the input (None: not found)."""
        ...

    async def match_title(self, title: str) -> ScholarPaper | None:
        """The closest paper to this title, or None."""
        ...
