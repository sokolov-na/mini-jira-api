# VPS deployment

Production uses the existing `compose.yaml` together with
`compose.production.yaml`. The override removes the build configuration,
requires immutable API and PostgreSQL image digests, adds an API healthcheck,
and bounds container logs to three 10 MB files per service.

The deployed files live in `/opt/mini-jira`. Production configuration lives in
`/etc/mini-jira/production.env`, owned by root with mode `0600`; its directory
has mode `0700`. Never print rendered Compose configuration or copy the env
file into Git. Generate unique hexadecimal DB and JWT secrets on the VPS.
Set all variables from `.env.docker.example`, plus `MINI_JIRA_IMAGE` and
`POSTGRES_IMAGE` containing verified `@sha256:` references.

`PASSWORD_RESET_FRONTEND_URL` is the frontend base URL, not the reset page;
the application appends `/reset-password`. Use a verified Resend sender and
real API key. Secure cookies remain enabled, with SameSite lax and an empty
Domain. An empty CORS allowlist is intentional until browser access is needed.

The API binds only to `127.0.0.1:8000` on the VPS. PostgreSQL publishes no host
port and persists its PostgreSQL 18 data under `/var/lib/postgresql` in the
`mini-jira_postgres_data` volume. Do not publish container ports on all host
interfaces: Docker port publishing can bypass UFW.

Run deployment commands on the VPS:

```bash
sudo bash /opt/mini-jira/ops/compose.sh config --quiet
sudo bash /opt/mini-jira/ops/compose.sh pull
sudo bash /opt/mini-jira/ops/compose.sh up -d --wait db
sudo bash /opt/mini-jira/ops/compose.sh run --rm --no-deps api alembic upgrade head
sudo bash /opt/mini-jira/ops/compose.sh up -d --wait api
sudo bash /opt/mini-jira/ops/compose.sh ps
curl --fail http://127.0.0.1:8000/health
```

Back up before every migration of an existing database. Never run `down -v`,
volume pruning, or production downgrade commands. Configuration validation
does not prove that an email provider accepts the configured key and sender.
Local HTTP health checks do not exercise Secure refresh cookies through HTTPS.

## Backups

Install `ops/mini-jira-backup.service` and `ops/mini-jira-backup.timer` in
`/etc/systemd/system`, then enable the timer. It runs daily at 03:15 Moscow time
with up to five minutes of jitter and catches up after downtime. Check it with:

```bash
sudo systemctl list-timers mini-jira-backup.timer
sudo systemctl start mini-jira-backup.service
sudo journalctl -u mini-jira-backup.service
```

The job uses PostgreSQL 18 `pg_dump` in custom format, compression level 3,
an exclusive lock, atomic rename, archive-list validation and SHA256 checksum.
`/var/backups/mini-jira` has mode `0700`; dump and checksum files have mode
`0600`. Files older than 14 days are rotated only after a successful dump.
The job refuses to start with less than 512 MiB free space. Monitor disk usage,
job failures and dump sizes; this threshold does not reserve space for a large
dump. Configuration secrets need their own protected recovery copy.

Verify restoration into a uniquely named disposable database, created from
`template0`, using `pg_restore --exit-on-error --single-transaction`. Check the
Alembic revision, tables and row counts against the source. Drop only that
disposable database after successful validation. Never restore over production
as a test. Repeat restoration tests after schema changes and periodically.

These local dumps cannot protect against VPS or disk loss. Before public use,
arrange encrypted copies on another machine or storage service, with separate
credentials and retention. Off-server transfer is not configured automatically.

## Startup and publication

Both services inherit `restart: unless-stopped`; Docker must be enabled at
boot. A manually stopped container stays stopped across daemon restarts.
The backup timer is enabled independently. Do not restart the VPS merely to
test deployment; an approved Docker restart can verify restart policies while
checking SSH and UFW afterward.

## Public HTTPS through Caddy

The alpha deployment uses Caddy on the VPS to proxy
`https://api.mini-jira.ru` to `http://127.0.0.1:8000`.
Cloudflare serves DNS only: the API hostname has an A record pointing to
`153.76.162.146`. The root domain and its existing Tunnel are independent.
The API Tunnel service is disabled; no Tunnel routes need to be deleted.

The deployed configuration is tracked in `ops/Caddyfile`; Caddy reads it as
`/etc/caddy/Caddyfile`. Its systemd service runs as the `caddy` user and is
enabled at boot. UFW allows incoming TCP 80 and 443 alongside the existing
SSH rule. Port 8000 remains bound to localhost and PostgreSQL has no published
port. HTTP redirects to HTTPS; Caddy obtains and renews a public certificate
automatically. Preserve `/var/lib/caddy`, which contains private TLS material,
outside Git with restricted access.

Caddy 2.11.7 was installed from the official GitHub release with SHA256
verification because the official Cloudsmith APT repository returned HTTP
402. Its APT source is retained but disabled. Caddy binary upgrades are manual;
certificate renewal is automatic. Use [official installation sources](https://caddyserver.com/docs/install).

Validate configuration before reloading Caddy and check `/health`, `/docs`,
and `/openapi.json` over HTTPS with certificate verification enabled. Save the
current DNS, UFW and Caddy configuration before changing network settings.

The API is an early alpha. Browser CORS configuration, frontend password-reset
routing, real email delivery and off-server backup recovery require their own
checks; successful HTTP health checks do not prove those flows.
