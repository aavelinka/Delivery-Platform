# API Gateway

Validates external JWT access tokens and forwards trusted identity headers to internal services.

External clients should call the gateway instead of service ports directly.

Public auth endpoints:

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`

All other proxied endpoints require an auth-service access token.
