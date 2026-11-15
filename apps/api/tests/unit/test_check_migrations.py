"""Spec 017 AC9: CI flags migrations that would break the API still running during a deploy."""

from pathlib import Path

from app.scripts.check_migrations import DEFAULT_DIR, check

HEAD = "from alembic import op\nimport sqlalchemy as sa\n\n"
SAFE_UPGRADE = "def upgrade() -> None:\n    op.execute(\"SET lock_timeout = '5s'\")\n"


def write(tmp: Path, name: str, body: str) -> Path:
    path = tmp / name
    path.write_text(HEAD + body)
    return path


def test_AC9_existing_migrations_pass() -> None:
    assert check(DEFAULT_DIR) == []


def test_AC9_flags_a_dropped_or_renamed_column(tmp_path: Path) -> None:
    write(tmp_path, "0030_a.py", SAFE_UPGRADE + '    op.drop_column("papers", "title")\n')
    write(
        tmp_path,
        "0031_b.py",
        SAFE_UPGRADE + '    op.alter_column("papers", "title", new_column_name="name")\n',
    )
    rename = '    op.execute("ALTER TABLE papers RENAME TO docs")\n'
    write(tmp_path, "0032_c.py", SAFE_UPGRADE + rename)
    problems = check(tmp_path)
    assert any("0030_a.py" in p and "drop_column" in p for p in problems)
    assert any("0031_b.py" in p and "renames" in p for p in problems)
    assert any("0032_c.py" in p and "RENAME TO" in p for p in problems)


def test_AC9_downgrade_and_marked_contract_steps_are_allowed(tmp_path: Path) -> None:
    write(
        tmp_path,
        "0030_a.py",
        SAFE_UPGRADE
        + '    op.add_column("papers", sa.Column("x", sa.Text()))\n\n\n'
        + 'def downgrade() -> None:\n    op.drop_column("papers", "x")\n',
    )
    write(
        tmp_path,
        "0031_b.py",
        "# contract: the API stopped reading papers.x in 0030's release\n"
        + SAFE_UPGRADE
        + '    op.drop_column("papers", "x")\n',
    )
    assert check(tmp_path) == []


def test_AC9_new_ddl_must_set_lock_timeout(tmp_path: Path) -> None:
    write(
        tmp_path,
        "0030_a.py",
        'def upgrade() -> None:\n    op.add_column("papers", sa.Column("x", sa.Text()))\n',
    )
    write(  # revisions before 0024 already ran in production
        tmp_path,
        "0020_old.py",
        'def upgrade() -> None:\n    op.add_column("papers", sa.Column("y", sa.Text()))\n',
    )
    assert check(tmp_path) == ["0030_a.py: changes existing tables without SET lock_timeout"]
