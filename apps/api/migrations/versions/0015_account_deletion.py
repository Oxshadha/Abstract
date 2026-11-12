"""Account deletion removes custom templates (spec 012 AC15).

The app only soft-deletes templates; the deletion worker removes a deleted account's custom
templates for good, so the worker role (only) may delete templates and their versions.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SQL = (
    "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'abstract_worker') "
    "THEN {action} DELETE ON templates, template_versions {direction} abstract_worker; "
    "END IF; END $$;"
)


def upgrade() -> None:
    op.execute(SQL.format(action="GRANT", direction="TO"))


def downgrade() -> None:
    op.execute(SQL.format(action="REVOKE", direction="FROM"))
