"""Object-storage key layout (spec 004 AC1, AC11). Every key is under the owning org's prefix."""

from uuid import UUID


def quarantine_key(org_id: UUID, upload_id: UUID) -> str:
    """Private landing place for raw uploads; never served to anyone."""
    return f"quarantine/{org_id}/{upload_id}.pdf"


def paper_prefix(org_id: UUID, paper_id: UUID) -> str:
    return f"papers/{org_id}/{paper_id}/"


def sanitized_key(org_id: UUID, paper_id: UUID) -> str:
    """The only copy that is processed, sent to models, shown and downloaded (D77)."""
    return f"{paper_prefix(org_id, paper_id)}sanitized.pdf"
