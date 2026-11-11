import socket

from app.worker.celery_app import celery_app


@celery_app.task(name="app.worker.tasks.delete_account")  # type: ignore[untyped-decorator]
def delete_account(user_id: str) -> dict[str, str]:
    """Account deletion (spec 002 AC3). Deleting papers, chunks and S3 objects lands with spec 004;
    the user is already disabled by the webhook, so no data is reachable meanwhile."""
    return {"user_id": user_id, "status": "disabled; content deletion pending spec 004"}


@celery_app.task(name="app.worker.tasks.ping")  # type: ignore[untyped-decorator]
def ping() -> dict[str, str | bool]:
    return {"pong": True, "worker": socket.gethostname()}
