"""Papers service (spec 004): uploads, finalize, listing, deletion."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from app.core.config import Settings
from app.core.context import Context
from app.core.errors import ProblemError
from app.modules.papers.keys import quarantine_key
from app.modules.papers.schemas import UploadRequest, UploadTicket
from app.ports.storage import Storage


async def create_upload(
    ctx: Context, body: UploadRequest, *, storage: Storage, settings: Settings
) -> UploadTicket:
    """AC1: a short-lived pre-signed POST for one PDF under the caller's org prefix."""
    if body.size_bytes > settings.upload_max_bytes:
        mb = settings.upload_max_bytes // (1024 * 1024)
        raise ProblemError(413, "file-too-large", f"PDFs can be up to {mb} MB.")
    identity = ctx.identity
    upload_id = uuid4()
    key = quarantine_key(identity.org_id, upload_id)
    ttl = settings.upload_url_ttl_seconds
    post = await storage.presigned_post(
        key,
        content_type=body.content_type,
        max_bytes=settings.upload_max_bytes,
        expires_seconds=ttl,
    )
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
    await ctx.session.execute(
        text(
            "INSERT INTO uploads (id, org_id, owner_id, quarantine_key, filename, declared_size,"
            " declared_sha256, expires_at) VALUES (:id, :org, :owner, :key, :name, :size, :sha,"
            " :exp)"
        ),
        {
            "id": upload_id,
            "org": identity.org_id,
            "owner": identity.user_id,
            "key": key,
            "name": body.filename,
            "size": body.size_bytes,
            "sha": body.sha256,
            "exp": expires_at,
        },
    )
    return UploadTicket(
        upload_id=upload_id, url=post.url, fields=post.fields, expires_at=expires_at
    )
