SHELL := /bin/sh

PYTHON ?= .venv/bin/python
API_GATEWAY_HOST_PORT ?= 8080
AUTH_SERVICE_HOST_PORT ?= 8003
ORDER_SERVICE_HOST_PORT ?= 8000
COURIER_SERVICE_HOST_PORT ?= 8001
NOTIFICATION_SERVICE_HOST_PORT ?= 8002
USER_SERVICE_HOST_PORT ?= 8004
TRACKING_SERVICE_HOST_PORT ?= 8005
ADMIN_SERVICE_HOST_PORT ?= 8006
PAYMENT_SERVICE_HOST_PORT ?= 8007
SERVICES := api-gateway auth-service user-service order-service courier-service tracking-service notification-service admin-service payment-service
POSTGRES_TEST_SERVICES := auth-service user-service order-service courier-service tracking-service notification-service payment-service

.PHONY: bootstrap install test-postgres-up test-postgres-down test-kafka-up test-kafka-down test-e2e-gateway lint mypy test-api-gateway test-admin-service test-payment-service test-platform-common test-kafka-contracts test-services-postgres test smoke-service-composes

bootstrap:
	python -m venv .venv
	$(PYTHON) -m ensurepip --upgrade
	$(PYTHON) -m pip install --upgrade pip setuptools wheel

install:
	$(PYTHON) -m pip install -e ./libs/platform-common
	$(PYTHON) -m pip install \
		-e "services/api-gateway[dev]" \
		-e "services/admin-service[dev]" \
		-e "services/auth-service[dev]" \
		-e "services/user-service[dev]" \
		-e "services/order-service[dev]" \
		-e "services/courier-service[dev]" \
		-e "services/tracking-service[dev]" \
		-e "services/notification-service[dev]" \
		-e "services/payment-service[dev]"

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

test-admin-service:
	(cd services/admin-service && ../../$(PYTHON) -m pytest -q)

test-payment-service:
	(cd services/payment-service && ../../$(PYTHON) -m pytest -q)

test-platform-common:
	($(PYTHON) -m pytest -q tests/platform_common)

test-kafka-contracts:
	($(PYTHON) -m pytest -q tests/contracts/test_kafka_contracts.py)

test-services-postgres:
	for service in $(POSTGRES_TEST_SERVICES); do \
		printf '\n==> pytest %s\n' "$$service"; \
		(cd services/$$service && ../../$(PYTHON) -m pytest -q) || exit 1; \
	done

test: test-api-gateway test-admin-service test-services-postgres test-platform-common test-kafka-contracts

smoke-service-composes:
	./scripts/smoke-service-compose.sh auth-service $(AUTH_SERVICE_HOST_PORT) smoke-auth-service
	./scripts/smoke-service-compose.sh user-service $(USER_SERVICE_HOST_PORT) smoke-user-service
	./scripts/smoke-service-compose.sh order-service $(ORDER_SERVICE_HOST_PORT) smoke-order-service
	./scripts/smoke-service-compose.sh courier-service $(COURIER_SERVICE_HOST_PORT) smoke-courier-service
	./scripts/smoke-service-compose.sh tracking-service $(TRACKING_SERVICE_HOST_PORT) smoke-tracking-service
	./scripts/smoke-service-compose.sh notification-service $(NOTIFICATION_SERVICE_HOST_PORT) smoke-notification-service
	./scripts/smoke-service-compose.sh admin-service $(ADMIN_SERVICE_HOST_PORT) smoke-admin-service
	./scripts/smoke-service-compose.sh payment-service $(PAYMENT_SERVICE_HOST_PORT) smoke-payment-service
	./scripts/smoke-service-compose.sh api-gateway $(API_GATEWAY_HOST_PORT) smoke-api-gateway
