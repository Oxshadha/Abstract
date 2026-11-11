"""Print the OpenAPI schema without needing real infrastructure (used by `make api-client`)."""

import json
import sys

from app.core.config import Settings
from app.factory import create_app


def main() -> None:
    settings = Settings(
        env="development",  # include dev routes so the client knows about them
        log_level="ERROR",  # stdout must contain only the schema
        database_url="postgresql+asyncpg://unused/unused",
        redis_url="redis://unused",
        s3_bucket="unused",
        _env_file=None,
    )
    app = create_app(settings, readiness_checks={})
    json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
