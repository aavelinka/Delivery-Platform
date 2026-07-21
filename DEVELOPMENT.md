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

For the full local observability stack around the same runtime, use:

```bash
make observability-up
```

That command runs the root stack through `docker-compose.observability.yml`,
enables OTLP export automatically, and provisions:

- `otel-collector`
- `Prometheus`
- `Jaeger`
- `Grafana`

Use `make observability-down` to stop that full-stack mode.

Optional OpenTelemetry trace export can still be enabled for either root compose
without the observability override or standalone service compose runs with:

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318/v1/traces
```

If `OTEL_ENABLED=true` is set without an OTLP endpoint, services fall back to
the console span exporter.

Default local UIs for the observability mode:

- Grafana: `http://localhost:3000`
- Jaeger: `http://localhost:16686`
- Prometheus: `http://localhost:9090`

Grafana is provisioned with:

- `Delivery Platform Overview`
- `Delivery Platform Business`

For password reset and a short smoke/demo flow, see
`observability/RUNBOOK.md`.

Kafka consumers in `order-service`, `courier-service`, `tracking-service`, and
`notification-service` also support bounded retries and service-level DLQ topics
through:

```bash
<SERVICE>_KAFKA_CONSUMER_MAX_RETRIES
<SERVICE>_KAFKA_CONSUMER_RETRY_BACKOFF_SECONDS
<SERVICE>_KAFKA_CONSUMER_DLQ_TOPIC
```

For the current Kafka consumer posture across services, query:

```bash
curl -H "Authorization: Bearer <admin-token>" \
  http://localhost:8080/admin/kafka/reliability
```

For local DLQ inspection and replay:

```bash
python scripts/kafka-dlq-tool.py peek --topic order-service.dlq --limit 5
python scripts/kafka-dlq-tool.py replay \
  --event-file /tmp/order-dlq-event.json \
  --replayed-by local-operator \
  --reason "fixed downstream bug" \
  --dry-run
```

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

For `platform-common` tracing and observability only:

```bash
make test-platform-common
```

That target covers the shared tracing context, telemetry bridge, DLQ replay
helpers, consumer retry/DLQ behavior, and graceful fallback behavior when the
OpenTelemetry SDK is unavailable locally.

## Event Flow

Core happy-path flow:

1. `order-service` creates an order and writes an outbox event.
2. `courier-service` consumes `order_created` and assigns an available courier.
3. `order-service` consumes courier events and updates order state.
4. `tracking-service` consumes order events and binds order ownership and courier access.
5. `notification-service` consumes order and courier events and creates in-app notifications.
6. `payment-service` publishes payment lifecycle events through its own outbox.

Failure-path rule:

- a poison Kafka message is retried a bounded number of times;
- if retries are exhausted and DLQ publish succeeds, the original offset is committed;
- if DLQ publish fails, the original offset is not committed, so the message is not lost.

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
