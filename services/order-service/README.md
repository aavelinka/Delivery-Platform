# Order Service

`order-service` is responsible for the order lifecycle in the delivery platform.

It owns order data, order status transitions, order event history, and publishes domain
events to Kafka.

It also consumes `couriers.events` and applies `courier_assigned` events to update
orders after `courier-service` assigns a courier.

## Responsibilities

- Create orders.
- Read order details.
- List orders with filters.
- Change order status.
- Cancel orders.
- Store order event history.
- Publish Kafka events:
  - `order_created`
  - `order_status_changed`
  - `order_cancelled`
  - `delivery_started`
  - `delivery_completed`
- Consume Kafka events:
  - `courier_assigned`

## Local Run

```bash
uvicorn app.main:app --reload
```

For the full platform stack, run from the repository root:

```bash
docker compose up --build
```

This service also has a standalone `docker-compose.yml` for isolated development.

To run migrations manually:

```bash
alembic upgrade head
```

## Environment

```env
ORDER_SERVICE_NAME=order-service
ORDER_ENVIRONMENT=local
ORDER_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/orders
ORDER_KAFKA_BOOTSTRAP_SERVERS=localhost:9092
ORDER_KAFKA_ENABLED=true
```

## API

- `POST /orders`
- `GET /orders/{order_id}`
- `GET /orders`
- `PATCH /orders/{order_id}/status`
- `POST /orders/{order_id}/cancel`
- `GET /orders/{order_id}/events`
