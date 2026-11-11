"""Background malware scan (D77, spec 004 AC16). Never in the user's path.

Scans the exact quarantined bytes (by ETag). On `infected`: the paper's derived data and
sanitized copy are removed, the original is moved to `infected/` for 7 days (lifecycle rule at
deployment) for review, the event is audited, and the paper shows a calm message. A scanner
outage only sets scan_status = error; the paper stays usable, as it is without a scanner.
"""

from uuid import UUID

from sqlalchemy import text

from app.core.logging import get_logger
from app.core.tenancy import set_tenant
from app.modules.papers.ingest import Deps, PaperGoneError
from app.modules.papers.jobs import transition
from app.modules.papers.keys import paper_prefix
from app.ports.storage import ObjectChangedError

SCAN_TASK = "app.worker.tasks.scan_paper"
INFECTED_MESSAGE = (
    "Our security check flagged this file, so it was removed. If you think this is a mistake, "
    "please contact support."
)
log = get_logger(__name__)


class ScanPendingError(Exception):
    """The scanner has not produced a result yet (GuardDuty); retried with backoff."""


def infected_key(org_id: UUID, paper_id: UUID) -> str:
    return f"infected/{org_id}/{paper_id}.pdf"


async def run_scan(deps: Deps, org_id: UUID, job_id: UUID) -> None:
    if deps.scanner is None:
        raise RuntimeError("scan job without a configured scanner")
    maker = deps.sessionmaker
    async with maker() as session, session.begin():
        await set_tenant(session, org_id)
        paper = (
            await session.execute(
                text(
                    "SELECT p.id, p.quarantine_key, p.quarantine_etag FROM jobs j"
                    " JOIN papers p ON p.id = j.paper_id WHERE j.id = :job"
                ),
                {"job": job_id},
            )
        ).first()
    if paper is None:
        raise PaperGoneError(str(job_id))
    try:
        data = await deps.storage.get_bytes(paper.quarantine_key, etag=paper.quarantine_etag)
    except ObjectChangedError:
        data = b""  # the ingest job rejects a replaced object; nothing to scan
    result = await deps.scanner.scan(paper.quarantine_key, data) if data else None
    if result is not None and result.verdict == "pending":
        raise ScanPendingError(paper.quarantine_key)

    async with maker() as session, session.begin():
        await set_tenant(session, org_id)
        if (
            await session.execute(
                text("SELECT 1 FROM papers WHERE id = :id FOR UPDATE"), {"id": paper.id}
            )
        ).first() is None:
            raise PaperGoneError(str(paper.id))
        infected = result is not None and result.verdict == "infected"
        if infected:
            assert result is not None
            await session.execute(text("DELETE FROM chunks WHERE paper_id = :p"), {"p": paper.id})
            await session.execute(
                text("DELETE FROM paper_pages WHERE paper_id = :p"), {"p": paper.id}
            )
            await session.execute(
                text(
                    "UPDATE jobs SET status = 'cancelled', finished_at = now(),"
                    " event_seq = event_seq + 1 WHERE paper_id = :p AND id <> :job"
                    " AND status IN ('queued', 'running', 'enqueue_failed')"
                ),
                {"p": paper.id, "job": job_id},
            )
            await session.execute(
                text(
                    "UPDATE papers SET scan_status = 'infected', status = 'failed',"
                    " text_status = 'failed', storage_key = NULL, error_message = :msg,"
                    " updated_at = now() WHERE id = :id"
                ),
                {"msg": INFECTED_MESSAGE, "id": paper.id},
            )
            await session.execute(
                text(
                    "INSERT INTO audit_log (org_id, action, resource_type, resource_id, metadata)"
                    " VALUES (:org, 'paper.infected', 'paper', :id,"
                    " jsonb_build_object('scanner', CAST(:scanner AS text),"
                    " 'signature', CAST(:sig AS text)))"
                ),
                {
                    "org": org_id,
                    "id": str(paper.id),
                    "scanner": deps.scanner.name,
                    "sig": result.signature,
                },
            )
        else:
            await session.execute(
                text(
                    "UPDATE papers SET scan_status = 'clean', updated_at = now()"
                    " WHERE id = :id AND scan_status <> 'infected'"
                ),
                {"id": paper.id},
            )
        await transition(session, job_id, "succeeded")

    if infected:
        await deps.storage.put_bytes(infected_key(org_id, paper.id), data, "application/pdf")
        await deps.storage.delete([paper.quarantine_key])
        await deps.storage.delete_prefix(paper_prefix(org_id, paper.id))
        log.warning("paper_infected", paper_id=str(paper.id), scanner=deps.scanner.name)


async def give_up(deps: Deps, org_id: UUID, job_id: UUID, reason: str) -> None:
    """Scanner unavailable after retries: record it; the paper stays usable (D77)."""
    async with deps.sessionmaker() as session, session.begin():
        await set_tenant(session, org_id)
        await transition(session, job_id, "failed", error=reason[:500])
        await session.execute(
            text(
                "UPDATE papers SET scan_status = 'error' WHERE id ="
                " (SELECT paper_id FROM jobs WHERE id = :job) AND scan_status = 'pending'"
            ),
            {"job": job_id},
        )
