# Security Policy

## Supported State

This repository currently targets active development on the default branch. Security
fixes should be applied there first and then backported only if release branches are
introduced later.

## Reporting a Vulnerability

Do not open a public issue for credential leaks, auth bypasses, or infrastructure
misconfiguration that could be exploited.

Until a dedicated security contact is published, report vulnerabilities through one
of these private channels:

- a private GitHub security advisory, if enabled for the repository
- direct contact with the repository owner or maintainer

Include:

- affected service or component
- reproduction steps
- impact assessment
- any temporary mitigation already known

## Secrets Handling

- Never commit real `.env` files or credentials.
- Use `.env.example` files as templates only.
- Rotate any secret immediately if it was ever exposed in commit history, logs, or screenshots.

## Scope to Review Carefully

Changes in these areas deserve extra scrutiny:

- JWT issuance and validation
- `GATEWAY_INTERNAL_SECRET` trust boundary
- role changes and privilege escalation paths
- event consumers that mutate order, courier, or tracking state
- Docker Compose defaults and publicly exposed ports
