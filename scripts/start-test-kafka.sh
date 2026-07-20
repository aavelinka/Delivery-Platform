#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
JWT_SECRET_KEY="${JWT_SECRET_KEY:-test-secret}"
GATEWAY_INTERNAL_SECRET="${GATEWAY_INTERNAL_SECRET:-test-gateway-secret}"

export JWT_SECRET_KEY
export GATEWAY_INTERNAL_SECRET

cd "$ROOT_DIR"

docker compose up -d zookeeper kafka

"$ROOT_DIR/scripts/wait-for-compose-services.sh" zookeeper kafka
