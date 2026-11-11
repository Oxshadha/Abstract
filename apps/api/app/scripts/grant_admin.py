"""Bootstrap the first platform admin (operator command, run with the OWNER database URL).

    MIGRATIONS_DATABASE_URL=... python -m app.scripts.grant_admin <clerk_user_id>

The API cannot create the first admin (no one can authorize it), so this is an explicit,
audited operator action.
"""

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def grant(subject: str) -> int:
    url = os.environ.get("MIGRATIONS_DATABASE_URL")
    if not url:
        print("MIGRATIONS_DATABASE_URL (owner role) is required", file=sys.stderr)
        return 2
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "UPDATE users SET platform_role = 'admin' WHERE clerk_user_id = :s "
                        "RETURNING id, personal_org_id"
                    ),
                    {"s": subject},
                )
            ).first()
            if row is None:
                print(f"No user with subject {subject!r}; they must sign in once first.")
                return 1
            if row.personal_org_id is not None:
                await conn.execute(
                    text("SELECT set_config('app.org_id', :o, true)"),
                    {"o": str(row.personal_org_id)},
                )
                await conn.execute(
                    text(
                        "INSERT INTO audit_log (org_id, action, resource_type, resource_id,"
                        " metadata) VALUES (:o, 'admin.role.bootstrap', 'user', :u,"
                        ' \'{"via": "operator command"}\'::jsonb)'
                    ),
                    {"o": row.personal_org_id, "u": str(row.id)},
                )
    finally:
        await engine.dispose()
    print(f"Granted admin to {subject}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(asyncio.run(grant(sys.argv[1])))
