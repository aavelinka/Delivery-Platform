# Courier Service

`courier-service` manages couriers, their availability, and assignments.

It consumes `orders.events`, reacts to `order_created`, assigns an available courier,
and publishes courier and assignment events.

## Responsibilities

- Create courier profiles.
- Read and update courier profiles.
- Change courier availability.
- List available couriers.
- Assign couriers to orders.
- Store assignment history.
- Publish Kafka events:
  - `courier_created`
  - `courier_updated`
  - `courier_availability_changed`
  - `courier_assigned`
  - `assignment_status_changed`
- Consume Kafka events:
  - `order_created`

## Local Run

For the full platform stack, run from the repository root:

```bash
docker compose up --build
```

This service also has a standalone `docker-compose.yml` for isolated development.

Manual migration:

```bash
alembic upgrade head
```

## API

- `POST /couriers`
- `GET /couriers/{courier_id}`
- `PATCH /couriers/{courier_id}`
- `PATCH /couriers/{courier_id}/availability`
- `GET /couriers/available`
- `POST /couriers/assignments`
- `PATCH /couriers/assignments/{assignment_id}/status`
- `GET /couriers/{courier_id}/assignments`
