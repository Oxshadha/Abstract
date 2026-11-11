#!/usr/bin/env bash
# UI source rules for apps/web/src:
#   D62    no em dashes, en dashes or emojis in user-facing source
#   003/2  no raw colours or font names outside the generated token files: colours and fonts
#          come only from design tokens (Tailwind token utilities or var(--...)).
# Usage: check-ui-text.sh            (check apps/web/src)
#        check-ui-text.sh --self-test (prove every rule catches a violation)
set -euo pipefail
cd "$(dirname "$0")/.."

python3 - "$@" <<'PY'
import pathlib, re, sys, tempfile

RULES = [
    ("em/en dash (D62)", re.compile("[–—]")),
    ("emoji (D62)", re.compile("[\U0001F300-\U0001FAFF]|[☀-➿]|[\U0001F1E6-\U0001F1FF]")),
    ("raw colour, use a token (003 AC2)", re.compile(
        r"#[0-9a-fA-F]{3,8}\b(?![-\w])|\b(?:rgba?|hsla?|oklch|oklab|lab|lch)\(")),
    ("Tailwind default palette class, use a token (003 AC2)", re.compile(
        r"\b(?:bg|text|border|ring|fill|stroke|from|to|via|outline|decoration|divide|placeholder)-"
        r"(?:red|blue|green|yellow|gray|slate|zinc|neutral|stone|orange|amber|lime|emerald|teal|"
        r"cyan|sky|indigo|violet|purple|fuchsia|pink|rose|black|white)(?:-\d{2,3})?\b")),
    ("font family outside tokens (003 AC2)", re.compile(
        r"font-family\s*:(?!\s*var\()|fontFamily\s*:\s*[\"'`]")),
]
# Generated token files, and the @font-face definitions (declaring a font is not using one).
GENERATED = {"tokens.css", "theme.css", "tokens.ts", "fonts.css"}
EXTS = {".ts", ".tsx", ".css", ".json", ".html"}


def scan(root: pathlib.Path) -> list[str]:
    bad = []
    for path in sorted(root.rglob("*")):
        if path.suffix not in EXTS or path.name == "schema.d.ts":
            continue
        if path.name in GENERATED and path.parent.name == "styles":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for label, rule in RULES:
                if rule.search(line):
                    bad.append(f"{path}:{n}: [{label}] {line.strip()}")
    return bad


if "--self-test" in sys.argv:
    samples = ["a — b", "ok \U0001F600", "color: #ff0000;", "rgb(0 0 0)",
               '<div className="bg-red-500">', 'style={{ fontFamily: "Arial" }}']
    with tempfile.TemporaryDirectory() as tmp:
        for i, sample in enumerate(samples):
            (pathlib.Path(tmp) / f"s{i}.tsx").write_text(sample + "\n", encoding="utf-8")
        found = scan(pathlib.Path(tmp))
    missed = [s for i, s in enumerate(samples) if not any(f"s{i}.tsx" in f for f in found)]
    clean_dir = tempfile.mkdtemp()
    (pathlib.Path(clean_dir) / "ok.tsx").write_text(
        '<div className="bg-surface text-text-secondary" style={{ color: "var(--x)" }} />\n'
        "// Figure #3 and see #section-2\n"
        "body { font-family: var(--font-ui); }\n", encoding="utf-8")
    false_positives = scan(pathlib.Path(clean_dir))
    if missed or false_positives:
        print("self-test FAILED", "missed:", missed, "false positives:", false_positives)
        sys.exit(1)
    print(f"self-test passed: {len(samples)} violations caught, no false positives")
    sys.exit(0)

problems = scan(pathlib.Path("apps/web/src"))
if problems:
    print("UI source check failed (see AGENTS.md design rules):")
    print("\n".join(problems))
    sys.exit(1)
print("UI source check passed")
PY
