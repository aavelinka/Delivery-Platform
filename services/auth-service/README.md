# Auth Service

`auth-service` manages users, password authentication, roles, and tokens.

## Responsibilities

- Register users.
- Login with email and password.
- Issue JWT access tokens.
- Issue and rotate refresh tokens.
- Return current authenticated user.
- Logout by revoking refresh token.
- Promote users to `courier` or `admin` via an admin-only endpoint.
- Accept trusted identity headers from `api-gateway` for protected internal auth endpoints.

## Local Run

For the full platform stack, run from the repository root:

```bash
docker compose up --build
```

Manual migration:

```bash
alembic upgrade head
```

Optional bootstrap admin:

```bash
export AUTH_BOOTSTRAP_ADMIN_EMAIL=admin@example.com
export AUTH_BOOTSTRAP_ADMIN_PASSWORD=replace-with-a-long-random-admin-password
```

## API

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`
- `PATCH /auth/users/{user_id}/role`
- `GET /auth/admin/summary`
