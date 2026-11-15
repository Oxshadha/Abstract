# Runbook: production

How Abstract runs in production and what to do when something needs attention. Decisions: D100 (host), D101 (answers survive leaving), spec 017.

## What runs where

| Part | Where | Notes |
|---|---|---|
| Website and API | https://abstract.oshadhakariyawasam.me | One origin; the API is under `/api` |
| Server | AWS EC2 `c7i-flex.large`, us-east-1, `3.234.207.173`, Ubuntu | Shared with QuantEdge; 3.7 GB RAM plus 4 GB swap |
| Containers | `/opt/abstract/src`, `infra/docker-compose.prod.yml` | `api`, `worker` (fast queue), `worker-bg` (background queues), `redis` |
| Web files | `/var/www/abstract` | Served by the host's nginx (`/etc/nginx/sites-available/abstract`), TLS by certbot |
| Database | Neon free, us-east-2, PostgreSQL 18 | App connects as `abstract_app` / `abstract_worker` (row-level security); migrations as the owner |
| Files and backups | Neon S3-compatible storage, bucket `s3-abstract` | `backups/` kept 7 days, `quarantine/` 1 day, `infected/` 7 days |
| Sign-in | Clerk (development instance for now) | Google, email and password, email codes |
| AI | Vertex AI (`global`), OpenRouter as fallback | OpenRouter needs credit to work as a fallback |
| Tracing | Langfuse Cloud | Metadata only (D76) |

**Settings and secrets** live in `/opt/abstract/.env.prod` and `/opt/abstract/.env.worker` (root only), and the Vertex key in `/opt/abstract/secrets/gcp_sa.json`. They are never in git. To change one: edit the file with `sudo`, then restart (below).

**Tables and figures are off** on this host (`ENRICHMENT_ENABLED=false`): the reader needs about 6 GB. Resize to 8 GB or more and set it to `true` to turn them on.

## Deploy

1. Merge to `main` and wait for CI to pass.
2. GitHub → **Actions → Deploy → Run workflow**, keep `main`, **Run**.
3. The workflow builds the web app, sends it with the code, and runs `infra/deploy/remote-deploy.sh` on the server:
   build image → migrate → switch → wait for `/readyz`. If the new version is not ready in 2 minutes it puts the previous image and web files back.

A deploy restarts the API and workers gracefully (spec 017 AC13): an answer being written finishes and is saved (uvicorn waits up to 20 s), and a summary in progress finishes or is put back on the queue (Celery warm shutdown, 90 s). There is one API container, so **new requests get a 502 for about 8 seconds** while it is replaced. Deploy at quiet times. Tested 2026-11-15 with a summary and an answer in flight: both completed.

**Roll back:** run the Deploy workflow again on the previous good commit (type its full SHA in the `ref` box). It must have passed CI. Migrations are expand-only, so older code runs on the newer schema. Tried 2026-11-15: back to `fc2fa62` and forward to `9b5fe09` again, about a minute each.

## Everyday commands (on the server)

```
ssh -i ~/.ssh/waypoint.pem ubuntu@3.234.207.173
cd /opt/abstract/src
C="sudo docker compose -f infra/docker-compose.prod.yml --project-directory ."
$C ps                                   # what is running
$C logs api --since 15m                 # API logs (JSON, one line per request)
$C logs worker --since 15m              # processing and summaries
$C up -d --force-recreate api worker worker-bg   # restart after a settings change
curl -s http://127.0.0.1:8000/api/v1/readyz      # database, Redis and storage checks
```

Make someone an admin (audited):
```
$C run --rm migrate python -m app.scripts.account <clerk_user_id> <email> --role admin --plan internal
```

## Cleanup of old records

Nightly at 03:00 UTC, `/etc/cron.d/abstract-prune` runs the retention task (spec 017 AC11):

```
0 3 * * * root cd /opt/abstract/src && docker compose -f infra/docker-compose.prod.yml --project-directory . run --rm migrate python -m app.scripts.prune >> /var/log/abstract-prune.log 2>&1
```

It deletes idempotency keys after 24 hours, AI usage rows after 13 months, and finished jobs after 13 months when a newer job of the same kind exists for that paper. The audit log is never pruned. Periods: `RETENTION_*` in `.env.prod`.

## Backups and restore

- **Nightly** at 02:30 UTC: `/opt/abstract/backup.sh` (from `/etc/cron.d/abstract-backup`) dumps the database and uploads it to `backups/`. Log: `/var/log/abstract-backup.log`.
- **RPO** (data that can be lost): up to 24 hours from the nightly dump; up to 6 hours for recent mistakes using Neon's own history (restore a branch to a point in time in the Neon console).
- **RTO** (time to be back): about 4 hours to rebuild the server from this runbook and restore the newest dump.
- **Drill:** `sudo /opt/abstract/restore-check.sh` restores the newest dump into a scratch database, compares row counts with the live one and drops it. First drill: 2026-11-14, every table matched.

**Restore the live database from a dump** (data loss since that dump):
1. Stop writers: `$C stop api worker worker-bg`.
2. In the Neon console, create a branch of the current state first (so the restore can be undone).
3. Download the dump (as `restore-check.sh` does) and run, with the owner URL:
   `docker run --rm -i -v /tmp/r:/backup postgres:18-alpine pg_restore --clean --if-exists --no-owner --no-privileges -d "<owner url>" /backup/latest.dump`
4. Start again: `$C up -d`, then check `/readyz` and sign in.

## Rebuild the server from nothing

1. A new Ubuntu host with Docker and the compose plugin, nginx and certbot; open ports 80 and 443 (and 22 for deploys).
2. Add a 4 GB swap file; create `/opt/abstract/{src,secrets}` and `/var/www/abstract`.
3. Put `.env.prod`, `.env.worker` and `secrets/gcp_sa.json` back (they are the only things not in git; keep a copy in a password manager).
4. Copy `infra/nginx/abstract.conf` to `/etc/nginx/sites-available/abstract`, link it, `sudo certbot --nginx -d abstract.oshadhakariyawasam.me`.
5. Point the DNS `A` record for `abstract` at the new address.
6. Add the deploy key to `~/.ssh/authorized_keys`, update the `DEPLOY_HOST` and `DEPLOY_KNOWN_HOSTS` secrets, and run the Deploy workflow.
7. Reinstall `backup.sh`, `restore-check.sh` and the cron line from `infra/deploy/`.

The data is in Neon and the storage bucket, not on the server, so a rebuild loses nothing.

## When something is wrong

| Symptom | Look at |
|---|---|
| Site down | `$C ps`; `sudo systemctl status nginx`; `/readyz` |
| Uploads stuck in Processing | `$C logs worker`; jobs in Admin → Jobs |
| A job stays `running` for hours | Admin → Jobs → Stuck, then Retry (audited). Its task was lost (for example in a restart while it waited to retry) |
| Answers fail | `$C logs api` for `llm_route_failed`; Vertex quota; OpenRouter credit |
| Sign-in fails | Clerk dashboard; `CLERK_ISSUER` and `CLERK_AUTHORIZED_PARTIES` in `.env.prod` |
| Server slow or out of memory | `free -h`; `docker stats`; QuantEdge shares the host. Normal peak: about 1.6 GB used with 20 answers at once (2026-11-15) |
| Answers slow to start when many people ask | At most 8 AI calls run at once per provider (`LLM_MAX_CONCURRENCY_PER_PROVIDER`); others wait their turn. 20 at once: first words p95 19 s |
| Spend climbing | Admin → Overview; the daily cap and the AI kill switch are there |
