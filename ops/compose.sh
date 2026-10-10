#!/usr/bin/env bash
set -euo pipefail

exec docker compose --project-name mini-jira \
  --env-file /etc/mini-jira/production.env \
  --project-directory /opt/mini-jira \
  -f /opt/mini-jira/compose.yaml \
  -f /opt/mini-jira/compose.production.yaml "$@"
