"""Summary templates (spec 006 AC1, D15, D38): versioned data, not prompts.

A template version holds the fields to extract; summaries record the exact version they used.
System templates (Quick Summary, Detailed Research Analysis) are shared and read-only; custom
templates (spec 010) belong to an org. Instructions are length-limited and reach the model only
as wrapped data (AGENTS rule 8).
"""

import json
import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemError
from app.modules.entitlements.service import Limits

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
    updated_at: datetime | None = None


class TemplateList(BaseModel):
    items: list[TemplateOut]


_SELECT = (
    "SELECT t.id, t.kind, t.name, t.description, v.version, v.id AS version_id, v.fields,"
    " t.updated_at"
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
        updated_at=row.updated_at,
    )


_VISIBLE = "t.deleted_at IS NULL AND (t.kind = 'system' OR t.owner_id = :o)"


async def list_templates(session: AsyncSession, owner_id: UUID) -> TemplateList:
    """System templates first, then the user's own (RLS also limits custom rows to the org)."""
    rows = (
        await session.execute(
            text(
                f"{_SELECT} WHERE {_VISIBLE} ORDER BY (t.kind = 'system') DESC, t.created_at, t.id"
            ),
            {"o": owner_id},
        )
    ).all()
    return TemplateList(items=[_out(r) for r in rows])


async def get_template(session: AsyncSession, owner_id: UUID, template_id: UUID) -> TemplateOut:
    row = (
        await session.execute(
            text(f"{_SELECT} WHERE t.id = :id AND {_VISIBLE}"), {"id": template_id, "o": owner_id}
        )
    ).first()
    if row is None:
        raise ProblemError(404, "template-not-found", "This template was not found.")
    return _out(row)


# --- custom templates (spec 010) -----------------------------------------------------------


class FieldIn(BaseModel):
    """A field as the builder sends it; `key` is absent for new fields and kept for old ones."""

    model_config = ConfigDict(extra="forbid")
    key: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,39}$")
    label: str = Field(min_length=1, max_length=60)
    instruction: str = Field(min_length=1, max_length=500)
    style: FieldStyle = "paragraph"
    required: bool = True


class TemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    fields: list[FieldIn] = Field(min_length=1, max_length=50)


class TemplateCreate(BaseModel):
    """Either a new template or a duplicate of an existing one (system or own)."""

    model_config = ConfigDict(extra="forbid")
    template: TemplateIn | None = None
    duplicate_of: UUID | None = None


class TemplateUpdate(TemplateIn):
    base_version: int = Field(ge=1)


def _slug(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:36]
    if not slug or not slug[0].isalpha():
        slug = f"field_{slug}".strip("_")
    return slug if len(slug) >= 2 else f"{slug}_x"


def build_fields(fields: list[FieldIn], limits: Limits) -> list[dict[str, Any]]:
    """AC3, AC4, AC9: limits from entitlements, unique labels, stable keys (kept when given,
    generated from the label when new and made unique)."""
    if len(fields) > limits.fields_per_template:
        raise ProblemError(
            409,
            "field-limit",
            f"A template can have up to {limits.fields_per_template} fields.",
        )
    labels = [f.label.strip().lower() for f in fields]
    if len(set(labels)) != len(labels):
        raise ProblemError(422, "duplicate-label", "Two fields have the same label.")
    taken = {f.key for f in fields if f.key}
    out = []
    for f in fields:
        if len(f.label) > limits.label_chars or len(f.instruction) > limits.instruction_chars:
            raise ProblemError(422, "too-long", "A field label or instruction is too long.")
        key = f.key
        if key is None:
            base, n = _slug(f.label), 2
            key = base
            while key in taken:
                key, n = f"{base[:36]}_{n}", n + 1
            taken.add(key)
        out.append(
            {
                "key": key,
                "label": f.label.strip(),
                "instruction": f.instruction.strip(),
                "style": f.style,
                "required": f.required,
            }
        )
    return out


async def _count_custom(session: AsyncSession, owner_id: UUID) -> int:
    count = (
        await session.execute(
            text(
                "SELECT count(*) FROM templates WHERE owner_id = :o AND kind = 'custom'"
                " AND deleted_at IS NULL"
            ),
            {"o": owner_id},
        )
    ).scalar_one()
    return int(count)


async def create(
    session: AsyncSession, org_id: UUID, owner_id: UUID, body: TemplateCreate, limits: Limits
) -> TemplateOut:
    if await _count_custom(session, owner_id) >= limits.custom_templates:
        raise ProblemError(
            409, "template-limit", f"You can keep up to {limits.custom_templates} custom templates."
        )
    if body.duplicate_of is not None:
        source = await get_template(session, owner_id, body.duplicate_of)
        name = f"{source.name} (copy)"[:80]
        description = source.description
        fields = [FieldIn(**f.model_dump()) for f in source.fields]
    elif body.template is not None:
        name, description, fields = (
            body.template.name,
            body.template.description,
            body.template.fields,
        )
    else:
        raise ProblemError(422, "missing-template", "Send a template or a template to duplicate.")
    name = await _free_name(session, owner_id, name.strip())
    built = build_fields(fields, limits)
    template_id = (
        await session.execute(
            text(
                "INSERT INTO templates (org_id, owner_id, kind, name, description)"
                " VALUES (:org, :o, 'custom', :n, :d) RETURNING id"
            ),
            {"org": org_id, "o": owner_id, "n": name, "d": description},
        )
    ).scalar_one()
    await session.execute(
        text(
            "INSERT INTO template_versions (org_id, template_id, version, fields)"
            " VALUES (:org, :t, 1, CAST(:f AS jsonb))"
        ),
        {"org": org_id, "t": template_id, "f": json.dumps(built)},
    )
    return await get_template(session, owner_id, template_id)


async def _free_name(
    session: AsyncSession, owner_id: UUID, name: str, skip: UUID | None = None
) -> str:
    """Names are unique per user: "Methods review" becomes "Methods review (2)" when taken."""
    existing = {
        str(n).lower()
        for n in (
            await session.execute(
                text(
                    "SELECT name FROM templates WHERE owner_id = :o AND kind = 'custom'"
                    " AND deleted_at IS NULL AND (CAST(:skip AS uuid) IS NULL OR id <> :skip)"
                ),
                {"o": owner_id, "skip": skip},
            )
        ).scalars()
    }
    candidate, n = name, 2
    while candidate.lower() in existing:
        candidate, n = f"{name[:74]} ({n})", n + 1
    return candidate


async def _own_custom(session: AsyncSession, owner_id: UUID, template_id: UUID) -> Any:
    row = (
        await session.execute(
            text(
                "SELECT id, kind, owner_id, current_version FROM templates WHERE id = :t"
                " AND deleted_at IS NULL FOR UPDATE"
            ),
            {"t": template_id},
        )
    ).first()
    if row is None or (row.kind == "custom" and row.owner_id != owner_id):
        raise ProblemError(404, "template-not-found", "This template was not found.")
    if row.kind == "system":
        raise ProblemError(
            403, "system-template", "System templates cannot be changed. Duplicate it to customize."
        )
    return row


async def update(
    session: AsyncSession,
    org_id: UUID,
    owner_id: UUID,
    template_id: UUID,
    body: TemplateUpdate,
    limits: Limits,
) -> TemplateOut:
    """AC5, AC10: a save creates the next version; a save from a stale base is refused."""
    row = await _own_custom(session, owner_id, template_id)
    if row.current_version != body.base_version:
        raise ProblemError(
            409,
            "stale-template",
            "This template was changed in another tab. Reload it to see the newer version.",
            extra={"current_version": row.current_version},
        )
    built = build_fields(body.fields, limits)
    version = row.current_version + 1
    name = await _free_name(session, owner_id, body.name.strip(), skip=template_id)
    await session.execute(
        text(
            "INSERT INTO template_versions (org_id, template_id, version, fields)"
            " VALUES (:org, :t, :v, CAST(:f AS jsonb))"
        ),
        {"org": org_id, "t": template_id, "v": version, "f": json.dumps(built)},
    )
    await session.execute(
        text(
            "UPDATE templates SET name = :n, description = :d, current_version = :v,"
            " updated_at = now() WHERE id = :t"
        ),
        {"n": name, "d": body.description, "v": version, "t": template_id},
    )
    return await get_template(session, owner_id, template_id)


async def delete(session: AsyncSession, owner_id: UUID, template_id: UUID) -> None:
    """AC2: hidden, not erased: summaries made with it keep their version and its name."""
    await _own_custom(session, owner_id, template_id)
    await session.execute(
        text("UPDATE templates SET deleted_at = now() WHERE id = :t"), {"t": template_id}
    )
