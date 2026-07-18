#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
PYTHON_BIN="${PYTHON:-$ROOT_DIR/.venv/bin/python}"
JWT_SECRET_KEY="${JWT_SECRET_KEY:-test-secret}"
GATEWAY_INTERNAL_SECRET="${GATEWAY_INTERNAL_SECRET:-test-gateway-secret}"

cleanup() {
  env \
    JWT_SECRET_KEY="$JWT_SECRET_KEY" \
    GATEWAY_INTERNAL_SECRET="$GATEWAY_INTERNAL_SECRET" \
    "$ROOT_DIR/scripts/stop-test-kafka.sh" >/dev/null 2>&1 || true
  env \
    JWT_SECRET_KEY="$JWT_SECRET_KEY" \
    GATEWAY_INTERNAL_SECRET="$GATEWAY_INTERNAL_SECRET" \
    "$ROOT_DIR/scripts/stop-test-postgres.sh" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

cd "$ROOT_DIR"

env \
  JWT_SECRET_KEY="$JWT_SECRET_KEY" \
  GATEWAY_INTERNAL_SECRET="$GATEWAY_INTERNAL_SECRET" \
  "$ROOT_DIR/scripts/start-test-postgres.sh"

env \
  JWT_SECRET_KEY="$JWT_SECRET_KEY" \
  GATEWAY_INTERNAL_SECRET="$GATEWAY_INTERNAL_SECRET" \
  "$ROOT_DIR/scripts/start-test-kafka.sh"

"$PYTHON_BIN" -m pytest -q tests/e2e/test_gateway_platform_flow.py
