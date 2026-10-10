#!/usr/bin/env bash
set -euo pipefail
umask 077

backup_dir=/var/backups/mini-jira
install -d -m 700 "$backup_dir"
exec 9>/run/lock/mini-jira-backup.lock
flock -n 9
available=$(df --output=avail -B1 "$backup_dir" | tail -n 1)
if (( available < 536870912 )); then
  echo 'Insufficient free disk space for PostgreSQL backup' >&2
  exit 1
fi

compose=(docker compose --project-name mini-jira
  --env-file /etc/mini-jira/production.env
  --project-directory /opt/mini-jira
  -f /opt/mini-jira/compose.yaml
  -f /opt/mini-jira/compose.production.yaml)
target="$backup_dir/mini-jira-$(date -u +%Y%m%dT%H%M%SZ).dump"
temporary="$target.tmp"
trap 'rm -f -- "$temporary"' EXIT
"${compose[@]}" exec -T db sh -c \
  'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -Z 3' > "$temporary"
test -s "$temporary"
"${compose[@]}" exec -T db pg_restore --list < "$temporary" > /dev/null
mv "$temporary" "$target"
sha256sum "$target" > "$target.sha256"
find "$backup_dir" -maxdepth 1 -type f -name 'mini-jira-*.dump*' -mtime +13 -delete
echo "PostgreSQL backup completed: $(basename "$target")"
