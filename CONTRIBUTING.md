# Contributing

This repository is organized as a multi-service Python backend. Keep changes small,
explicit, and verifiable.

## Prerequisites

- Python `3.12`
- Docker and Docker Compose
- GNU Make

## Local Setup

From the repository root:

```bash
make bootstrap
make install
```

Create a local `.env` from `.env.example` and set at least:

- `JWT_SECRET_KEY`
- `GATEWAY_INTERNAL_SECRET`

Optional for role bootstrap in `auth-service`:

- `AUTH_BOOTSTRAP_ADMIN_EMAIL`
- `AUTH_BOOTSTRAP_ADMIN_PASSWORD`
- `AUTH_BOOTSTRAP_ADMIN_FULL_NAME`

## Development Workflow

Run the shared test databases:

```bash
make test-postgres-up
```

Verify the full repository:

```bash
make lint
make mypy
make test
make test-e2e-gateway
```

Stop test databases when finished:

```bash
make test-postgres-down
```

For isolated service smoke checks:

```bash
make smoke-service-composes
```

## Change Expectations

- Preserve service boundaries. Do not couple one service directly to another service's database.
- Prefer event-driven integration through Kafka and outbox where cross-service coordination is needed.
- Keep public contracts explicit: request/response schemas, auth rules, and event payloads should be covered by tests.
- Update `README.md` and the affected service `README.md` when behavior or setup changes.

## Tests Before PR

At minimum, run the narrowest checks that prove your change:

- changed service tests
- relevant cross-service tests
- `make lint`

Before merging broader work, run the full suite:

```bash
make lint
make mypy
make test
```

## Pull Requests

- Describe the user-visible or system-visible change.
- Call out environment, schema, or event-contract changes explicitly.
- Include the exact verification commands you ran.
- Prefer follow-up PRs over bundling unrelated refactors into one branch.
