"""Move a user to another plan from the command line (spec 012 AC10), until the admin screens
exist (spec 011). Run with the OWNER database URL; audited like the admin endpoint.

    MIGRATIONS_DATABASE_URL=... python -m app.scripts.set_plan <email or clerk_user_id> <plan>
"""

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def set_plan(who: str, plan: str) -> int:
    url = os.environ.get("MIGRATIONS_DATABASE_URL")
    if not url:
        print("MIGRATIONS_DATABASE_URL (owner role) is required", file=sys.stderr)
        return 2
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            if (
                await conn.execute(text("SELECT 1 FROM plans WHERE id = :p"), {"p": plan})
            ).first() is None:
                print(f"No plan {plan!r} (free, pro or internal).", file=sys.stderr)
                return 1
            row = (
                await conn.execute(
                    text(
                        "UPDATE users SET plan_id = :p WHERE lower(email) = lower(:w)"
                        " OR clerk_user_id = :w"
                        " RETURNING id, personal_org_id,"
                        " (SELECT plan_id FROM users u WHERE u.id = users.id) AS before"
                    ),
                    {"p": plan, "w": who},
                )
            ).first()
            if row is None:
                print(f"No user {who!r}; they must sign in once first.", file=sys.stderr)
                return 1
            if row.personal_org_id is not None:
                await conn.execute(
                    text("SELECT set_config('app.org_id', :o, true)"),
                    {"o": str(row.personal_org_id)},
                )
                await conn.execute(
                    text(
                        "INSERT INTO audit_log (org_id, action, resource_type, resource_id,"
                        " metadata) VALUES (:o, 'admin.users.plan', 'user', :u,"
                        " jsonb_build_object('from', CAST(:b AS text), 'to', CAST(:p AS text),"
                        " 'via', 'operator command'))"
                    ),
                    {"o": row.personal_org_id, "u": str(row.id), "b": row.before, "p": plan},
                )
    finally:
        await engine.dispose()
    print(f"{who} is now on the {plan} plan")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(asyncio.run(set_plan(sys.argv[1], sys.argv[2])))
