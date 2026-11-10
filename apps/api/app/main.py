"""ASGI entrypoint: `uvicorn app.main:app`.

Fails fast with a readable message on bad config (AC7).
"""

import sys

from pydantic import ValidationError

from app.core.config import get_settings
from app.factory import create_app

try:
    settings = get_settings()
except ValidationError as exc:
    missing = ", ".join(
        ".".join(str(p) for p in e["loc"]).upper() or e["msg"] for e in exc.errors()
    )
    sys.stderr.write(
        f"\nConfiguration error: {missing}\n{exc}\n"
        "Copy .env.example to .env at the repo root and fill in the values.\n\n"
    )
    raise SystemExit(1) from exc

app = create_app(settings)
