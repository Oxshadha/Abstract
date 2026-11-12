"""Register a Clerk user in Abstract with a role and plan (operator command).

    MIGRATIONS_DATABASE_URL=... python -m app.scripts.account <clerk_user_id> <email>
        [--name "Display Name"] [--role user|admin] [--plan free|pro|internal]

Sign-in itself (email, password, Google) lives in Clerk; this sets up the matching account here,
the same way the first sign-in would (personal workspace, owner membership), then sets the
platform role and plan. Safe to run again: it updates the role and plan. Audited.
"""

import argparse
import asyncio
import json
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.identity.service import provision
from app.ports.auth import Principal


async def setup(subject: str, email: str, name: str | None, role: str, plan: str) -> int:
    url = os.environ.get("MIGRATIONS_DATABASE_URL")
    if not url:
        print("MIGRATIONS_DATABASE_URL (owner role) is required", file=sys.stderr)
        return 2
    if not subject.startswith("user_"):
        print(
            "The first argument is the Clerk user ID (user_...), from Clerk > Users.",
            file=sys.stderr,
        )
        return 2
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine)() as session, session.begin():
            if (
                await session.execute(text("SELECT 1 FROM plans WHERE id = :p"), {"p": plan})
            ).first() is None:
                print(f"No plan {plan!r} (free, pro or internal).", file=sys.stderr)
                return 1
            account = await provision(session, Principal(subject=subject, email=email, name=name))
            await session.execute(
                text("UPDATE users SET platform_role = :r, plan_id = :p WHERE id = :u"),
                {"r": role, "p": plan, "u": account.user_id},
            )
            await session.execute(
                text(
                    "INSERT INTO audit_log (org_id, action, resource_type, resource_id, metadata)"
                    " VALUES (:o, 'account.setup', 'user', :u, CAST(:m AS jsonb))"
                ),
                {
                    "o": account.org_id,
                    "u": str(account.user_id),
                    "m": json.dumps({"role": role, "plan": plan, "via": "operator command"}),
                },
            )
    finally:
        await engine.dispose()
    print(f"{email} ({subject}) is set up as {role} on the {plan} plan")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("subject", help="Clerk user ID (user_...)")
    parser.add_argument("email")
    parser.add_argument("--name", default=None)
    parser.add_argument("--role", choices=["user", "admin"], default="user")
    parser.add_argument("--plan", default="free")
    args = parser.parse_args(argv)
    return asyncio.run(setup(args.subject, args.email, args.name, args.role, args.plan))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
