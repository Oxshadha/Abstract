#!/usr/bin/env bash
# Nightly database backup (spec 017 AC16, D100). Runs on the host from /etc/cron.d/abstract-backup.
#
# Neon's free plan keeps only 6 hours of history (assumption D12), so once a day the whole
# database is dumped (pg_dump custom format, compressed) and uploaded to the app's storage bucket
# under backups/. A bucket lifecycle rule deletes dumps after 7 days (owner: 7 days). Nothing is
# kept on the host. Restore: infra/deploy/restore-check.sh shows the steps and checks a dump.
set -euo pipefail

ENV_FILE=/opt/abstract/.env.prod
STAMP=$(date -u +%Y%m%dT%H%MZ)
WORK=$(mktemp -d /tmp/abstract-backup.XXXXXX)
trap 'rm -rf "$WORK"' EXIT

owner_url() {
  # The owner role: a full dump must read every table, so it cannot run as the RLS-bound app role.
  grep '^MIGRATIONS_DATABASE_URL=' "$ENV_FILE" | cut -d= -f2- \
    | sed 's#postgresql+asyncpg://#postgresql://#; s#ssl=require#sslmode=require#'
}

# Client tools must be at least the server's version (Neon runs PostgreSQL 18).
docker run --rm postgres:18-alpine pg_dump --format=custom --compress=6 --no-owner --no-privileges \
  "$(owner_url)" > "$WORK/abstract-$STAMP.dump"
SIZE=$(stat -c %s "$WORK/abstract-$STAMP.dump")
[ "$SIZE" -gt 1024 ] || { echo "backup suspiciously small: $SIZE bytes" >&2; exit 1; }

# Upload with the app image's boto3 and the app's own storage settings.
docker run --rm -i --user 0 --env-file "$ENV_FILE" -v "$WORK:/backup:ro" abstract-api:prod python - "$STAMP" <<'PY'
import os, sys
import boto3
from botocore.config import Config
stamp = sys.argv[1]
s3 = boto3.client("s3", endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
                  region_name=os.environ.get("S3_REGION"),
                  aws_access_key_id=os.environ.get("S3_ACCESS_KEY_ID"),
                  aws_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY"),
                  config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"))
key = f"backups/abstract-{stamp}.dump"
s3.upload_file(f"/backup/abstract-{stamp}.dump", os.environ["S3_BUCKET"], key)
print("uploaded", key)
PY
echo "backup $STAMP ok: $SIZE bytes"
