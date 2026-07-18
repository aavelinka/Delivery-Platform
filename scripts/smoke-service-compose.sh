#!/usr/bin/env sh
set -eu

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <service-dir> <host-port> <project-name>" >&2
  exit 1
fi

SERVICE_DIR="$1"
HOST_PORT="$2"
PROJECT_NAME="$3"

ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
COMPOSE_FILE="$ROOT_DIR/services/$SERVICE_DIR/docker-compose.yml"
OPENAPI_URL="http://127.0.0.1:$HOST_PORT/openapi.json"
JWT_SECRET_KEY="${JWT_SECRET_KEY:-test-secret}"
GATEWAY_INTERNAL_SECRET="${GATEWAY_INTERNAL_SECRET:-test-gateway-secret}"

cleanup() {
  env \
    JWT_SECRET_KEY="$JWT_SECRET_KEY" \
    GATEWAY_INTERNAL_SECRET="$GATEWAY_INTERNAL_SECRET" \
    docker compose \
      -p "$PROJECT_NAME" \
      -f "$COMPOSE_FILE" \
      down -v --remove-orphans >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

env \
  JWT_SECRET_KEY="$JWT_SECRET_KEY" \
  GATEWAY_INTERNAL_SECRET="$GATEWAY_INTERNAL_SECRET" \
  docker compose \
    -p "$PROJECT_NAME" \
    -f "$COMPOSE_FILE" \
    up -d --build

attempt=0
until curl -fsS "$OPENAPI_URL" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "service $SERVICE_DIR did not become ready on $OPENAPI_URL" >&2
    env \
      JWT_SECRET_KEY="$JWT_SECRET_KEY" \
      GATEWAY_INTERNAL_SECRET="$GATEWAY_INTERNAL_SECRET" \
      docker compose \
        -p "$PROJECT_NAME" \
        -f "$COMPOSE_FILE" \
        logs --tail=200
    exit 1
  fi
  sleep 2
done

echo "service $SERVICE_DIR is reachable at $OPENAPI_URL"
