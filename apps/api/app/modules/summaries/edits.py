"""Editing summaries (spec 006 AC9, AC12). Edits are versioned and guarded by If-Match; they are
never overwritten by regeneration or gap-fill (D15). Retrying a failed summary starts a new job.
"""

from uuid import UUID

from sqlalchemy import text

from app.core.context import Context
from app.core.errors import ProblemError


def parse_version(if_match: str) -> int:
    raw = if_match.strip().removeprefix("W/").strip('"').split("-", 1)[0]
    try:
        return int(raw)
    except ValueError as exc:
        raise ProblemError(400, "bad-if-match", "If-Match must be the summary version.") from exc


async def _lock(ctx: Context, summary_id: UUID, version: int) -> None:
    row = (
        await ctx.session.execute(
            text(
                "SELECT s.version FROM summaries s JOIN papers p ON p.id = s.paper_id"
                " WHERE s.id = :s AND p.owner_id = :o FOR UPDATE OF s"
            ),
            {"s": summary_id, "o": ctx.identity.user_id},
        )
    ).first()
    if row is None:
        raise ProblemError(404, "summary-not-found", "This summary was not found.")
    if row.version != version:
        raise ProblemError(
            412,
            "stale-version",
            "This summary changed in another tab. Reload it or keep your copy.",
        )


async def _bump_version(ctx: Context, summary_id: UUID) -> int:
    version: int = (
        await ctx.session.execute(
            text(
                "UPDATE summaries SET version = version + 1, event_seq = event_seq + 1,"
                " updated_at = now() WHERE id = :s RETURNING version"
            ),
            {"s": summary_id},
        )
    ).scalar_one()
    return version


async def edit_field(ctx: Context, summary_id: UUID, key: str, value: str, version: int) -> int:
    await _lock(ctx, summary_id, version)
    updated = await ctx.session.execute(
        text(
            "UPDATE summary_fields SET value = :v, edited = true, updated_at = now()"
            " WHERE summary_id = :s AND key = :k RETURNING id"
        ),
        {"v": value, "s": summary_id, "k": key},
    )
    if updated.first() is None:
        raise ProblemError(404, "field-not-found", "This field was not found.")
    return await _bump_version(ctx, summary_id)


async def reset_field(ctx: Context, summary_id: UUID, key: str, version: int) -> int:
    await _lock(ctx, summary_id, version)
    updated = await ctx.session.execute(
        text(
            "UPDATE summary_fields SET value = generated_value, edited = false,"
            " updated_at = now() WHERE summary_id = :s AND key = :k RETURNING id"
        ),
        {"s": summary_id, "k": key},
    )
    if updated.first() is None:
        raise ProblemError(404, "field-not-found", "This field was not found.")
    return await _bump_version(ctx, summary_id)


async def retry(ctx: Context, summary_id: UUID) -> UUID:
    """A failed summary gets a new job; fields already shown are kept and refreshed."""
    row = (
        await ctx.session.execute(
            text(
                "SELECT s.status, s.paper_id FROM summaries s JOIN papers p ON p.id = s.paper_id"
                " WHERE s.id = :s AND p.owner_id = :o FOR UPDATE OF s"
            ),
            {"s": summary_id, "o": ctx.identity.user_id},
        )
    ).first()
    if row is None:
        raise ProblemError(404, "summary-not-found", "This summary was not found.")
    if row.status != "failed":
        raise ProblemError(409, "not-failed", "Only a failed summary can be retried.")
    job_id: UUID = (
        await ctx.session.execute(
            text(
                "INSERT INTO jobs (org_id, paper_id, kind, step) VALUES"
                " (:org, :p, 'summary', 'summary') RETURNING id"
            ),
            {"org": ctx.identity.org_id, "p": row.paper_id},
        )
    ).scalar_one()
    await ctx.session.execute(
        text(
            "UPDATE summaries SET status = 'queued', job_id = :j, error_message = NULL,"
            " event_seq = event_seq + 1 WHERE id = :s"
        ),
        {"j": job_id, "s": summary_id},
    )
    return job_id
