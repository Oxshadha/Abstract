"""Spec 002 AC9 (Neon pooled vs direct endpoints) and AC12 (no implicit lazy loading)."""

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.db import engine_options, is_pooled_endpoint
from app.core.models import EXPLICIT_LAZY, Base, rel

POOLED = "postgresql+asyncpg://u:p@ep-cool-123-pooler.eu-central-1.aws.neon.tech/db"
DIRECT = "postgresql+asyncpg://u:p@ep-cool-123.eu-central-1.aws.neon.tech/db"


def test_AC9_pooled_endpoint_is_detected() -> None:
    assert is_pooled_endpoint(POOLED)
    assert not is_pooled_endpoint(DIRECT)
    assert not is_pooled_endpoint("postgresql+asyncpg://u:p@localhost:5432/db")


def test_AC9_pooled_endpoint_disables_statement_caches() -> None:
    url, options = engine_options(POOLED)
    assert "prepared_statement_cache_size=0" in url
    assert options["connect_args"]["statement_cache_size"] == 0
    names = {options["connect_args"]["prepared_statement_name_func"]() for _ in range(3)}
    assert len(names) == 3  # unique statement names on shared server connections


def test_AC9_direct_endpoint_keeps_defaults() -> None:
    url, options = engine_options(DIRECT)
    assert url == DIRECT
    assert "connect_args" not in options


def _implicit_lazy_relationships(base: type[DeclarativeBase]) -> list[str]:
    return [
        f"{mapper.class_.__name__}.{prop.key}"
        for mapper in base.registry.mappers
        for prop in mapper.relationships
        if prop.lazy not in EXPLICIT_LAZY
    ]


def test_AC12_no_mapped_relationship_lazy_loads_implicitly() -> None:
    import app.modules  # noqa: F401 - import feature modules so their models register

    assert _implicit_lazy_relationships(Base) == []


def test_AC12_rel_defaults_to_raise_and_the_check_catches_default_lazy() -> None:
    class IsolatedBase(DeclarativeBase):  # separate registry: never touches the app's models
        pass

    class Parent(IsolatedBase):
        __tablename__ = "ac12_parent"
        id: Mapped[int] = mapped_column(primary_key=True)
        good = rel("Child", viewonly=True)
        bad = relationship("Child", viewonly=True)  # implicit lazy="select"

    class Child(IsolatedBase):
        __tablename__ = "ac12_child"
        id: Mapped[int] = mapped_column(primary_key=True)
        parent_id: Mapped[int] = mapped_column(ForeignKey("ac12_parent.id"))

    IsolatedBase.registry.configure()
    assert Parent.good.property.lazy == "raise"
    assert _implicit_lazy_relationships(IsolatedBase) == ["Parent.bad"]
    assert Child.__tablename__ == "ac12_child"
