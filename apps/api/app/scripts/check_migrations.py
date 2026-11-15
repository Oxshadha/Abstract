"""CI guard for migrations that would break the running API during a deploy (spec 017 AC9).

The deploy migrates first and switches the API second, so for a minute the previous API runs on
the new schema. A migration's upgrade() must therefore only expand: no dropped or renamed columns
or tables. A contract step (removing what an earlier release stopped using) is allowed when the
file says so with a line `# contract: <why the previous release no longer uses it>`.

From revision 0024 on, an upgrade() that changes existing tables also sets `lock_timeout`, so a
migration waiting on a busy table fails fast instead of queueing every query behind it.

    python -m app.scripts.check_migrations [versions_dir]
"""

import ast
import re
import sys
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "migrations" / "versions"
BREAKING_OPS = {"drop_column", "drop_table", "rename_table"}
BREAKING_SQL = re.compile(r"\b(DROP\s+COLUMN|DROP\s+TABLE|RENAME\s+(COLUMN|TO))\b", re.IGNORECASE)
CONTRACT = re.compile(r"^\s*#\s*contract:\s*\S", re.MULTILINE)
LOCKING_OPS = {"add_column", "alter_column", "create_index", "create_foreign_key", "execute"}
LOCK_TIMEOUT_FROM = 24  # earlier revisions already ran in production


def _upgrade(tree: ast.Module) -> ast.FunctionDef | None:
    return next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"), None
    )


def _calls(fn: ast.FunctionDef) -> list[ast.Call]:
    return [
        n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    ]


def breaking_steps(source: str) -> list[str]:
    """What upgrade() does that the previous API version could trip over."""
    upgrade = _upgrade(ast.parse(source))
    if upgrade is None:
        return []
    found: list[str] = []
    for node in _calls(upgrade):
        assert isinstance(node.func, ast.Attribute)
        name = node.func.attr
        if name in BREAKING_OPS:
            found.append(f"line {node.lineno}: op.{name}")
        elif name == "alter_column" and any(k.arg == "new_column_name" for k in node.keywords):
            found.append(f"line {node.lineno}: alter_column renames a column")
        elif name == "execute":
            for arg in node.args:
                text = arg.value if isinstance(arg, ast.Constant) else None
                if isinstance(text, str) and (match := BREAKING_SQL.search(text)):
                    found.append(f"line {node.lineno}: SQL {match.group(0).upper()}")
    return found


def needs_lock_timeout(source: str) -> bool:
    """upgrade() touches existing tables but never sets lock_timeout."""
    upgrade = _upgrade(ast.parse(source))
    if upgrade is None or "lock_timeout" in ast.unparse(upgrade):
        return False
    return any(
        isinstance(n.func, ast.Attribute) and n.func.attr in LOCKING_OPS for n in _calls(upgrade)
    )


def _revision(path: Path) -> int:
    match = re.match(r"(\d+)_", path.name)
    return int(match.group(1)) if match else 0


def check(directory: Path) -> list[str]:
    problems: list[str] = []
    for path in sorted(directory.glob("*.py")):
        source = path.read_text()
        steps = breaking_steps(source)
        if steps and not CONTRACT.search(source):
            problems.extend(f"{path.name} {step}" for step in steps)
        if _revision(path) >= LOCK_TIMEOUT_FROM and needs_lock_timeout(source):
            problems.append(f"{path.name}: changes existing tables without SET lock_timeout")
    return problems


def main() -> int:
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    problems = check(directory)
    for problem in problems:
        print(problem)
    if problems:
        print(
            "\nA migration must not break the API that is still running during a deploy:"
            " expand now and contract in a later release (mark that step"
            " '# contract: <why nothing uses it any more>'), and start upgrade() with"
            " op.execute(\"SET lock_timeout = '5s'\").",
            file=sys.stderr,
        )
        return 1
    print(f"migrations ok ({len(list(directory.glob('*.py')))} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
