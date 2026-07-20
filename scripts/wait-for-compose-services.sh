#!/usr/bin/env sh
set -eu

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 <service> [<service> ...]" >&2
  exit 1
fi

ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
WAIT_TIMEOUT_SECONDS="${COMPOSE_WAIT_TIMEOUT_SECONDS:-90}"
END_TIME=$(( $(date +%s) + WAIT_TIMEOUT_SECONDS ))

cd "$ROOT_DIR"

for service in "$@"; do
  printf 'Waiting for %s to become ready...\n' "$service"
  while :; do
    CONTAINER_ID="$(docker compose ps -q "$service" 2>/dev/null || true)"
    if [ -n "$CONTAINER_ID" ]; then
      STATUS="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER_ID" 2>/dev/null || true)"
      if [ "$STATUS" = "healthy" ] || [ "$STATUS" = "running" ]; then
        break
      fi
    fi

    if [ "$(date +%s)" -ge "$END_TIME" ]; then
      echo "Timed out waiting for $service to become ready" >&2
      docker compose ps "$service" >&2 || true
      exit 1
    fi

    sleep 1
  done
done
