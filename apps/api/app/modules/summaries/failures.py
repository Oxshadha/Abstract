"""When a summary job gives up (spec 006 AC7): the summary fails with a calm message and keeps
any fields already shown. The paper, its text index and chat are unaffected (rule 10)."""

from uuid import UUID

from sqlalchemy import text

from app.core.tenancy import set_tenant
from app.modules.papers.ingest import Deps
from app.modules.papers.jobs import InvalidTransitionError, transition

SUMMARY_FAILED = "The summary could not be created. Your paper and chat are still available."


async def give_up(deps: Deps, org_id: UUID, job_id: UUID, reason: str) -> None:
    async with deps.sessionmaker() as session, session.begin():
        await set_tenant(session, org_id)
        try:
            await transition(session, job_id, "failed", error=reason[:500])
        except InvalidTransitionError:
            return
        await session.execute(
            text(
                "UPDATE summaries SET status = 'failed', error_message = :m,"
                " event_seq = event_seq + 1, updated_at = now() WHERE job_id = :j"
            ),
            {"m": SUMMARY_FAILED, "j": job_id},
        )
