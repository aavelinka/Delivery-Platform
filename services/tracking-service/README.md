# Tracking Service

Stores courier locations and exposes current and historical tracking data.

## Endpoints

- `POST /tracking/locations`
- `GET /tracking/orders/{order_id}`
- `GET /tracking/orders/{order_id}/history`
- `GET /tracking/couriers/{courier_user_id}`

Location payloads use `courier_user_id`, the auth-service user id for the courier.
When `user_id` is present, order tracking reads are limited to that customer,
the assigned courier, or an admin.
