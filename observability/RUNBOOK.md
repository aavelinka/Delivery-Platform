# Observability Runbook

## Start The Full Stack

Use the root observability mode when you want traces, metrics, and dashboards
around the same local runtime:

```bash
JWT_SECRET_KEY=test-secret \
GATEWAY_INTERNAL_SECRET=test-gateway-secret \
make observability-up
```

Stop it with:

```bash
make observability-down
```

## Local UIs

- Grafana: `http://localhost:3000`
- Jaeger: `http://localhost:16686`
- Prometheus: `http://localhost:9090`

## Grafana Access

Default credentials are `admin` / `admin` unless overridden in `.env`.

If `admin` / `admin` does not work, the usual reason is an existing
`grafana_data` volume with an older password. Reset it in-place:

```bash
docker exec -it avelinapython-grafana-1 \
  grafana cli admin reset-admin-password NewLocalGrafana123!
```

If you want a full clean Grafana state instead:

```bash
make observability-down
docker volume rm avelinapython_grafana_data
JWT_SECRET_KEY=test-secret \
GATEWAY_INTERNAL_SECRET=test-gateway-secret \
make observability-up
```

## Provisioned Dashboards

- `Delivery Platform Overview`
  Focuses on HTTP throughput, latency, and 5xx behavior across services.
- `Delivery Platform Business`
  Focuses on domain state: orders, courier coverage, notifications, user
  profile coverage, tracking activity, auth roles, and payment status mix.

## Quick Smoke Flow

1. Open Grafana and confirm both dashboards are present.
2. Open Jaeger and verify the service list contains:
   `api-gateway`, `auth-service`, `user-service`, `order-service`,
   `courier-service`, `tracking-service`, `notification-service`,
   `payment-service`, `admin-service`.
3. Hit the gateway health endpoint:

```bash
curl http://localhost:8080/health
```

4. Confirm Prometheus can see request metrics:

```bash
curl --get \
  --data-urlencode 'query=http_requests_total{service="api-gateway",path="/health"}' \
  http://localhost:9090/api/v1/query
```

5. Open the `Delivery Platform Overview` dashboard and verify the gateway
   request appears.

## Useful PromQL Checks

Verify business metrics are present:

```bash
curl --get \
  --data-urlencode 'query=delivery_orders_total' \
  http://localhost:9090/api/v1/query

curl --get \
  --data-urlencode 'query=delivery_payments_by_status' \
  http://localhost:9090/api/v1/query

curl --get \
  --data-urlencode 'query=delivery_notifications_by_channel' \
  http://localhost:9090/api/v1/query
```

Check traces made it to Jaeger:

```bash
curl http://localhost:16686/api/services
```

## Operator Checks

Kafka reliability posture remains available through the admin API:

```bash
curl -H "Authorization: Bearer <admin-token>" \
  http://localhost:8080/admin/kafka/reliability
```

DLQ inspection and replay tooling:

```bash
python scripts/kafka-dlq-tool.py peek --topic order-service.dlq --limit 5
python scripts/kafka-dlq-tool.py replay \
  --event-file /tmp/order-dlq-event.json \
  --replayed-by local-operator \
  --reason "fixed downstream bug" \
  --dry-run
```
