# Notification Service

`notification-service` stores notifications and creates them from Kafka events.

It subscribes to:

- `orders.events`
- `couriers.events`

## Responsibilities

- Create notifications from system events.
- Store notification history.
- Mark notifications as read.
- Expose notifications by user.

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

- `POST /notifications`
- `GET /notifications/{notification_id}`
- `GET /notifications/users/{user_id}`
- `PATCH /notifications/{notification_id}/read`
