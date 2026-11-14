#!/usr/bin/env bash
# Restore drill (spec 017 AC16): prove the newest backup can be restored, without touching the
# live database. Downloads the newest dump from backups/, restores it into a scratch database
# `restore_check` on the same Neon project, compares row counts of key tables with the live
# database, then drops the scratch database.
#
# A real restore uses the same pg_restore command against the live database after stopping the
# API and workers (see docs/runbook.md).
set -euo pipefail

ENV_FILE=/opt/abstract/.env.prod
WORK=$(mktemp -d /tmp/abstract-restore.XXXXXX)
trap 'rm -rf "$WORK"' EXIT

OWNER=$(grep '^MIGRATIONS_DATABASE_URL=' "$ENV_FILE" | cut -d= -f2- \
  | sed 's#postgresql+asyncpg://#postgresql://#; s#ssl=require#sslmode=require#')
SCRATCH=$(printf '%s' "$OWNER" | sed -E 's#/([^/?]+)\?#/restore_check?#')
PG=(docker run --rm -i -v "$WORK:/backup" postgres:18-alpine)

docker run --rm -i --user 0 --env-file "$ENV_FILE" -v "$WORK:/backup" abstract-api:prod python - <<'PY'
import os
import boto3
from botocore.config import Config
s3 = boto3.client("s3", endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
                  region_name=os.environ.get("S3_REGION"),
                  aws_access_key_id=os.environ.get("S3_ACCESS_KEY_ID"),
                  aws_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY"),
                  config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"))
items = s3.list_objects_v2(Bucket=os.environ["S3_BUCKET"], Prefix="backups/").get("Contents", [])
newest = max(items, key=lambda o: o["LastModified"])
s3.download_file(os.environ["S3_BUCKET"], newest["Key"], "/backup/latest.dump")
print("restoring", newest["Key"], newest["Size"], "bytes")
PY

"${PG[@]}" psql "$OWNER" -q -c "DROP DATABASE IF EXISTS restore_check" -c "CREATE DATABASE restore_check"
"${PG[@]}" pg_restore --no-owner --no-privileges --exit-on-error -d "$SCRATCH" /backup/latest.dump

COUNTS="select 'users', count(*) from users union all select 'papers', count(*) from papers
        union all select 'messages', count(*) from messages union all select 'notes', count(*) from paper_notes"
echo "table     live  restored"
paste <("${PG[@]}" psql "$OWNER" -tA -F' ' -c "$COUNTS") <("${PG[@]}" psql "$SCRATCH" -tA -F' ' -c "$COUNTS" | cut -d' ' -f2)

"${PG[@]}" psql "$OWNER" -q -c "DROP DATABASE restore_check"
echo "restore check done (scratch database dropped)"
