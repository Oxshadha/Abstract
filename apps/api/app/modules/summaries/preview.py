"""Try a template on a paper (spec 010 AC7): the summary pipeline without saving anything.

Same prompt, schema and field streaming as a real summary (spec 006), run in the API process so
the builder sees fields as they are written. One model call, counted toward the spend caps.
"""

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemError
from app.modules.llm.prompts import using
from app.modules.summaries.generate import (
    META_KEYS,
    SUMMARIZE,
    _clean_field,
    messages_for,
    summary_schema,
)
from app.modules.summaries.streaming import FieldStream
from app.modules.summaries.templates import TemplateField
from app.ports.llm import LLMGateway
from app.ports.storage import Storage


def sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def paper_for_preview(
    session: AsyncSession, owner_id: UUID, paper_id: UUID
) -> tuple[str, str]:
    row = (
        await session.execute(
            text("SELECT filename, storage_key FROM papers WHERE id = :p AND owner_id = :o"),
            {"p": paper_id, "o": owner_id},
        )
    ).first()
    if row is None:
        raise ProblemError(404, "paper-not-found", "This paper was not found.")
    if row.storage_key is None:
        raise ProblemError(
            409, "paper-not-ready", "This paper is still being prepared. Try again in a moment."
        )
    return str(row.filename), str(row.storage_key)


async def preview_events(
    *,
    storage: Storage,
    gateway: LLMGateway,
    storage_key: str,
    filename: str,
    fields: list[TemplateField],
) -> AsyncIterator[str]:
    pdf = await storage.get_bytes(storage_key)  # the sanitized copy only (D77)
    keys = {f.key for f in fields}
    stream = FieldStream()
    with using(SUMMARIZE):
        async for chunk in gateway.stream(
            task="summarize",
            messages=messages_for(fields, filename, pdf),
            json_schema=summary_schema(fields),
        ):
            completed = stream.feed(chunk.text) if chunk.text else {}
            for key, raw in completed.items():
                if key in META_KEYS or key not in keys:
                    continue
                value, status, evidence = _clean_field(raw)
                yield sse(
                    "field",
                    {
                        "key": key,
                        "value": value,
                        "status": status,
                        "evidence": [{"page": p, "quote": q} for p, q in evidence],
                    },
                )
    yield sse("done", {"fields": len([k for k in keys if k in stream.done])})
