# Auth Service

`auth-service` manages users, password authentication, roles, and tokens.

## Responsibilities

- Register users.
- Login with email and password.
- Issue JWT access tokens.
- Issue and rotate refresh tokens.
- Return current authenticated user.
- Logout by revoking refresh token.

## Local Run

For the full platform stack, run from the repository root:

```bash
docker compose up --build
```

Manual migration:

```bash
alembic upgrade head
```

## API

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`
