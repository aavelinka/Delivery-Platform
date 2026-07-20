# Admin Service

`admin-service` provides an admin-only operational overview of the delivery platform.

It does not own business data directly. Instead, it aggregates admin summaries from
other services over internal HTTP, including `payment-service`, and derives
high-level platform analytics from those summaries.

## Endpoints

- `GET /admin/overview`
- `GET /admin/services/health`
- `GET /admin/analytics`

## Local Run

For the full platform stack, run from the repository root:

```bash
docker compose up --build
```

Standalone compose is available for isolated development. It expects the other
services to be reachable on host ports.
