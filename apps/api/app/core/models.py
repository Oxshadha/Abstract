"""ORM base (spec 002 AC12). Relationships must never lazy-load implicitly.

Use `rel(...)`, which defaults to lazy="raise": touching an unloaded relationship raises instead
of silently issuing one query per row (N+1). List endpoints load what they need explicitly with
`selectinload`. A test fails if any mapped relationship uses implicit lazy loading.
"""

from typing import Any

from sqlalchemy.orm import DeclarativeBase, relationship

# Loading strategies that never issue surprise queries on attribute access.
EXPLICIT_LAZY = frozenset({"raise", "raise_on_sql", "selectin", "joined", "noload"})


class Base(DeclarativeBase):
    pass


def rel(*args: Any, **kwargs: Any) -> Any:
    kwargs.setdefault("lazy", "raise")
    return relationship(*args, **kwargs)
