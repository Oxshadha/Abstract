#!/usr/bin/env bash
# Runs ON the production host (spec 017 AC12, D100), started by .github/workflows/deploy.yml.
#
#   remote-deploy.sh <release-id>
#
# Expects /tmp/abstract-release/src.tar (git archive of the commit) and web.tar (the built web
# app). Order matters so a failure leaves the old version serving:
#   1. unpack the code beside the current one        nothing running is touched yet
#   2. build the API image under a new tag           old image still serves
#   3. run migrations (expand-only, AC9)             old API keeps working with the new schema
#   4. switch: retag, restart API and workers, swap the web files
#   5. wait for /readyz; on failure, roll back to the previous image and web files
set -euo pipefail

RELEASE="${1:?usage: remote-deploy.sh <release-id>}"
INBOX=/tmp/abstract-release
ROOT=/opt/abstract
WEB=/var/www/abstract
COMPOSE=(docker compose -f infra/docker-compose.prod.yml --project-directory .)

log() { printf '[deploy %s] %s\n' "$RELEASE" "$*"; }

test -s "$INBOX/src.tar" && test -s "$INBOX/web.tar" || { log "release files missing"; exit 2; }

log "1/5 unpack code"
rm -rf "$ROOT/src.next" && mkdir -p "$ROOT/src.next"
tar -x -C "$ROOT/src.next" -f "$INBOX/src.tar"
rm -rf "$WEB.next" && mkdir -p "$WEB.next"
tar -x -C "$WEB.next" -f "$INBOX/web.tar" 2>/dev/null
test -s "$WEB.next/app.html" || { log "web build has no app.html"; exit 3; }

log "2/5 build API image"
docker build -q --target prod -t "abstract-api:$RELEASE" "$ROOT/src.next/apps/api" >/dev/null

log "3/5 migrate"
# The compose migrate service uses abstract-api:prod; run the new image's migrations directly.
docker run --rm --env-file "$ROOT/.env.prod" --cap-drop ALL --security-opt no-new-privileges:true \
  "abstract-api:$RELEASE" alembic upgrade head

log "4/5 switch"
PREVIOUS=$(docker image inspect abstract-api:prod --format '{{.Id}}' 2>/dev/null || true)
docker tag "abstract-api:$RELEASE" abstract-api:prod
rm -rf "$ROOT/src.prev" && mv "$ROOT/src" "$ROOT/src.prev" && mv "$ROOT/src.next" "$ROOT/src"
cd "$ROOT/src"
"${COMPOSE[@]}" up -d --no-build --force-recreate api worker worker-bg >/dev/null
rm -rf "$WEB.prev" && mv "$WEB" "$WEB.prev" && mv "$WEB.next" "$WEB"

log "5/5 health"
for _ in $(seq 1 30); do
  if curl -fs -m 5 http://127.0.0.1:8000/api/v1/readyz >/dev/null; then
    log "ready: $(curl -s http://127.0.0.1:8000/api/v1/readyz)"
    docker image prune -f --filter "label!=keep" >/dev/null 2>&1 || true
    rm -rf "$INBOX"
    exit 0
  fi
  sleep 4
done

log "not ready after 2 minutes: rolling back"
if [ -n "$PREVIOUS" ]; then docker tag "$PREVIOUS" abstract-api:prod; fi
rm -rf "$WEB" && mv "$WEB.prev" "$WEB"
rm -rf "$ROOT/src" && mv "$ROOT/src.prev" "$ROOT/src"
cd "$ROOT/src" && "${COMPOSE[@]}" up -d --no-build --force-recreate api worker worker-bg >/dev/null
exit 1
