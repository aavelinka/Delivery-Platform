#!/usr/bin/env sh
set -eu

JWT_SECRET_KEY="${JWT_SECRET_KEY:-test-secret}"
GATEWAY_INTERNAL_SECRET="${GATEWAY_INTERNAL_SECRET:-test-gateway-secret}"

export JWT_SECRET_KEY
export GATEWAY_INTERNAL_SECRET

docker compose stop \
  orders-postgres \
  couriers-postgres \
  notifications-postgres \
  auth-postgres \
  users-postgres \
  tracking-postgres
