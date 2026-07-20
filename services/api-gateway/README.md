# API Gateway

Validates external JWT access tokens and forwards trusted identity headers to internal services.

External clients should call the gateway instead of service ports directly.

Public auth endpoints:

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`

Other proxied domains include `/users`, `/orders`, `/couriers`, `/tracking`,
`/notifications`, `/payments` and `/admin`.

All non-public proxied endpoints require an auth-service access token.
