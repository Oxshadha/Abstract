"""Summary templates (spec 006 AC1, D15, D38): versioned data, not prompts.

A template version holds the fields to extract; summaries record the exact version they used.
System templates (Quick Summary, Detailed Research Analysis) are shared and read-only; custom
templates (spec 010) belong to an org. Instructions are length-limited and reach the model only
as wrapped data (AGENTS rule 8).
"""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemError

FieldStyle = Literal["paragraph", "bullets", "short"]
QUICK_SUMMARY_ID = UUID("00000000-0000-4000-8000-000000000001")
DETAILED_ANALYSIS_ID = UUID("00000000-0000-4000-8000-000000000002")


class TemplateField(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    label: str = Field(min_length=1, max_length=60)
    instruction: str = Field(min_length=1, max_length=500)
    style: FieldStyle = "paragraph"
    required: bool = True


class TemplateOut(BaseModel):
    id: UUID
    kind: Literal["system", "custom"]
    name: str
    description: str
    version: int
    version_id: UUID
    fields: list[TemplateField]


class TemplateList(BaseModel):
    items: list[TemplateOut]


_SELECT = (
    "SELECT t.id, t.kind, t.name, t.description, v.version, v.id AS version_id, v.fields"
    " FROM templates t JOIN template_versions v ON v.template_id = t.id"
    " AND v.version = t.current_version"
)


def _out(row: Any) -> TemplateOut:
    return TemplateOut(
        id=row.id,
        kind=row.kind,
        name=row.name,
        description=row.description,
        version=row.version,
        version_id=row.version_id,
        fields=[TemplateField.model_validate(f) for f in row.fields],
    )


async def list_templates(session: AsyncSession) -> TemplateList:
    """System templates first, then the org's own (RLS limits custom rows to the org)."""
    rows = (
        await session.execute(
            text(f"{_SELECT} ORDER BY (t.kind = 'system') DESC, t.created_at, t.id")
        )
    ).all()
    return TemplateList(items=[_out(r) for r in rows])


async def get_template(session: AsyncSession, template_id: UUID) -> TemplateOut:
    row = (await session.execute(text(f"{_SELECT} WHERE t.id = :id"), {"id": template_id})).first()
    if row is None:
        raise ProblemError(404, "template-not-found", "This template was not found.")
    return _out(row)
