#!/usr/bin/env bash
# D62: no em dashes, en dashes or emojis in user-facing frontend source.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 - <<'PY'
import pathlib, re, sys

BANNED = re.compile(
    "[–—]"            # en dash, em dash
    "|[\U0001F300-\U0001FAFF]"  # pictographs, emoticons, symbols
    "|[☀-➿]"          # misc symbols & dingbats
    "|[\U0001F1E6-\U0001F1FF]"  # flags
)
root = pathlib.Path("apps/web/src")
bad = []
for path in root.rglob("*"):
    if path.suffix not in {".ts", ".tsx", ".css", ".json", ".html"} or path.name == "schema.d.ts":
        continue
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if BANNED.search(line):
            bad.append(f"{path}:{n}: {line.strip()}")
if bad:
    print("UI text check failed: remove em/en dashes and emojis (AGENTS.md, D62):")
    print("\n".join(bad))
    sys.exit(1)
print("UI text check passed")
PY
