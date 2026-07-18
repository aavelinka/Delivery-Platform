SHELL := /bin/sh

PYTHON ?= .venv/bin/python
SERVICES := api-gateway auth-service user-service order-service courier-service tracking-service notification-service
POSTGRES_TEST_SERVICES := auth-service user-service order-service courier-service tracking-service notification-service

.PHONY: bootstrap install test-postgres-up test-postgres-down test-kafka-up test-kafka-down test-e2e-gateway lint mypy test-api-gateway test-services-postgres test smoke-service-composes

bootstrap:
	python -m venv .venv
	$(PYTHON) -m ensurepip --upgrade
	$(PYTHON) -m pip install --upgrade pip setuptools wheel

install:
	$(PYTHON) -m pip install -e libs/platform-common
	$(PYTHON) -m pip install \
		-e "services/api-gateway[dev]" \
		-e "services/auth-service[dev]" \
		-e "services/user-service[dev]" \
		-e "services/order-service[dev]" \
		-e "services/courier-service[dev]" \
		-e "services/tracking-service[dev]" \
		-e "services/notification-service[dev]"

test-postgres-up:
	./scripts/start-test-postgres.sh

test-postgres-down:
	./scripts/stop-test-postgres.sh

test-kafka-up:
	./scripts/start-test-kafka.sh

test-kafka-down:
	./scripts/stop-test-kafka.sh

test-e2e-gateway:
	./scripts/run-gateway-e2e.sh

lint:
	for service in $(SERVICES); do \
		printf '\n==> ruff %s\n' "$$service"; \
		(cd services/$$service && ../../$(PYTHON) -m ruff check .) || exit 1; \
	done

mypy:
	for service in $(SERVICES); do \
		printf '\n==> mypy %s\n' "$$service"; \
		(cd services/$$service && ../../$(PYTHON) -m mypy app) || exit 1; \
	done

test-api-gateway:
	(cd services/api-gateway && ../../$(PYTHON) -m pytest -q)

test-services-postgres:
	for service in $(POSTGRES_TEST_SERVICES); do \
		printf '\n==> pytest %s\n' "$$service"; \
		(cd services/$$service && ../../$(PYTHON) -m pytest -q) || exit 1; \
	done

test: test-api-gateway test-services-postgres

smoke-service-composes:
	./scripts/smoke-service-compose.sh auth-service 8003 smoke-auth-service
	./scripts/smoke-service-compose.sh user-service 8004 smoke-user-service
	./scripts/smoke-service-compose.sh order-service 8000 smoke-order-service
	./scripts/smoke-service-compose.sh courier-service 8001 smoke-courier-service
	./scripts/smoke-service-compose.sh tracking-service 8005 smoke-tracking-service
	./scripts/smoke-service-compose.sh notification-service 8002 smoke-notification-service
	./scripts/smoke-service-compose.sh api-gateway 8080 smoke-api-gateway
