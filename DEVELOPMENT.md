# Development Guide

## Repository Layout

- `services/` contains independently runnable FastAPI services.
- `libs/platform-common/` contains shared auth and outbox helpers.
- `test_support/` contains shared PostgreSQL test utilities.
- `scripts/` contains local development and smoke-test helpers.

## Service Boundaries

Each service owns its own schema and migrations. Cross-service coordination should
follow this order of preference:

1. synchronous external traffic through `api-gateway`
2. asynchronous integration through Kafka events
3. shared libraries only for framework-level concerns, not shared business state

Direct cross-service database access is out of bounds.

## Local Run Modes

### Full platform

```bash
docker compose up --build
```

Only `api-gateway` is exposed publicly on port `8080`. Internal services run inside
the Compose network and trust headers signed by `GATEWAY_INTERNAL_SECRET`.
`admin-service` also runs internally in the full stack and is expected to be
reached through the gateway in normal external flows. `payment-service` should
also be reached through `api-gateway` in the full stack rather than by calling
its container directly.

### Single service

Each implemented service has its own `docker-compose.yml` under `services/<name>/`.
Use this when iterating on one service in isolation.

In standalone service compose files, only the service HTTP port is published to
the host. PostgreSQL, Kafka, and ZooKeeper stay internal to that stack, so
standalone runs do not fight with the root `docker-compose.yml` over DB or
broker ports.

### Tests

Test suites use PostgreSQL, not SQLite. Start test databases first:

```bash
make test-postgres-up
```

Default host ports:

- `5433` courier-service
- `5434` notification-service
- `5435` auth-service
- `5436` user-service
- `5437` tracking-service
- `5438` order-service
- `5439` payment-service

For the full external flow through `api-gateway` and Kafka:

```bash
make test-e2e-gateway
```

That target starts test PostgreSQL and Kafka, launches services locally, runs a
real gateway-driven scenario, and tears the infrastructure down automatically.

For cross-service event payload compatibility only:

```bash
make test-kafka-contracts
```

That target runs contract checks from `tests/contracts/test_kafka_contracts.py`
against real producer and consumer code paths with isolated PostgreSQL schemas.

## Event Flow

Core happy-path flow:

1. `order-service` creates an order and writes an outbox event.
2. `courier-service` consumes `order_created` and assigns an available courier.
3. `order-service` consumes courier events and updates order state.
4. `tracking-service` consumes order events and binds order ownership and courier access.
5. `notification-service` consumes order and courier events and creates in-app notifications.
6. `payment-service` publishes payment lifecycle events through its own outbox.

When changing event payloads, update:

- producer tests
- consumer tests
- cross-service chain tests
- cross-service contract tests
- affected README contract text

## Auth Model

- External clients authenticate with JWT access tokens issued by `auth-service`.
- `api-gateway` validates JWTs and forwards trusted identity headers internally.
- Internal services must reject spoofed direct access unless `GATEWAY_INTERNAL_SECRET`
  is present.

## Done Definition

A change is not complete until it includes:

- code
- tests
- documentation updates when contracts or setup changed
- a clean `make lint`
- a clean `make test`
