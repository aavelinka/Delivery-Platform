# Delivery Platform

Микросервисная backend-платформа для управления доставкой еды и посылок.

Проект моделирует реальный delivery backend: пользователь регистрируется, создает
заказ, система назначает курьера, заказ проходит по статусам, курьер отправляет
геопозицию, а пользователь получает уведомления.

## Current Status

Сейчас в репозитории реализованы и подключены в общий `docker-compose.yml`:

- `api-gateway`
- `admin-service`
- `auth-service`
- `user-service`
- `order-service`
- `courier-service`
- `tracking-service`
- `notification-service`
- `payment-service`

Перед запуском создайте локальный `.env` из `.env.example` и задайте:

- `JWT_SECRET_KEY`
- `GATEWAY_INTERNAL_SECRET`
- `AUTH_BOOTSTRAP_ADMIN_EMAIL`
- `AUTH_BOOTSTRAP_ADMIN_PASSWORD`

Во внешнем контуре используется только `api-gateway` на порту `8080`.
Остальные сервисы доступны внутри Docker Compose сети и принимают доверенные
identity headers, подписанные `GATEWAY_INTERNAL_SECRET`.

Host-порты HTTP-сервисов можно переопределять через `.env`, например
`API_GATEWAY_HOST_PORT` или `ORDER_SERVICE_HOST_PORT`.

## Что Работает Сейчас

- регистрация, логин, access token, refresh token rotation, logout, `/auth/me`
  и admin-only смена роли пользователя;
- роли `customer`, `courier`, `admin`;
- пользовательские профили и адреса доставки;
- создание, чтение, список, отмена заказов и история событий заказа;
- смена статусов заказа с валидацией переходов;
- профили курьеров, доступность, назначения и смена статусов assignment;
- автоматическое назначение курьера по событию `order_created`;
- текущая геолокация курьера и история перемещений по заказу;
- инициализация tracking-данных из order events;
- ручные и автоматические in-app уведомления из Kafka событий;
- платежи по заказам, payment lifecycle переходы и audit trail;
- API gateway с JWT-проверкой, retry и basic rate limiting;
- `admin-service` с admin-only overview, cross-service health/summary агрегацией
  и derived business analytics;
- admin/debug обзор Kafka consumer reliability через
  `GET /admin/kafka/reliability` и service-level admin endpoints;
- единый `x-request-id` и structured HTTP request logging во всех сервисах;
- distributed tracing через `traceparent`, `x-trace-id` и `metadata.trace`
  в Kafka events/outbox, с optional OpenTelemetry OTLP export;
- готовый local observability stack через `docker-compose.observability.yml`
  с `otel-collector`, `Prometheus`, `Jaeger` и `Grafana`;
- bounded Kafka consumer retries, poison-message isolation и DLQ fallback
  в `order-service`, `courier-service`, `tracking-service`,
  `notification-service`;
- CLI tooling для инспекции и replay DLQ событий через
  `python scripts/kafka-dlq-tool.py`;
- Prometheus-style `/metrics` endpoint во всех сервисах;
- outbox pattern для публикации событий в Kafka в `order-service`,
  `courier-service`, `tracking-service` и `payment-service`.

## Технологический Стек

Текущая реализация:

- Python 3.12
- FastAPI
- Pydantic v2
- SQLAlchemy 2.0
- Alembic
- PostgreSQL
- Kafka
- Docker
- Docker Compose
- OpenTelemetry
- pytest
- Ruff
- mypy

Есть в инфраструктуре или планируются, но пока не используются как часть
основного runtime:

- MongoDB: в текущем коде не используется.

## Архитектура

Система разделена на независимые сервисы. Каждый сервис владеет своей схемой
данных и не ходит напрямую в базу другого сервиса.

Основной межсервисный обмен идет через Kafka-события.

Синхронный HTTP используется для внешнего API через `api-gateway`.

Правило идентичности:

- `courier-service` хранит id профиля курьера как `courier_id`;
- межсервисные order/tracking API используют `courier_user_id`:
  это `auth-service` user id из JWT `sub`;
- `tracking-service` узнает владельца заказа и привязанного курьера из
  `orders.events`, после чего ограничивает чтение только владельцу заказа,
  назначенному курьеру или администратору.

## Сервисы

### api-gateway

Единая внешняя точка входа. Валидирует JWT, снимает spoofed headers и
проксирует запросы во внутренние сервисы.

### auth-service

Отвечает за регистрацию, логин, JWT access token, refresh token rotation,
logout и роли.

При наличии `AUTH_BOOTSTRAP_ADMIN_EMAIL` и `AUTH_BOOTSTRAP_ADMIN_PASSWORD`
на старте автоматически создается bootstrap admin.

База данных: PostgreSQL.

### user-service

Отвечает за пользовательский профиль и адреса доставки.

База данных: PostgreSQL.

### order-service

Центральный сервис системы. Отвечает за заказы, их статусы, отмену и историю
событий. Публикует order events и синхронизируется с courier events.

База данных: PostgreSQL.

### courier-service

Отвечает за курьеров, их доступность, назначения на заказы и assignment flow.

База данных: PostgreSQL.

### tracking-service

Отвечает за текущую геолокацию курьера и историю перемещений по заказу.
В текущей архитектуре намеренно использует PostgreSQL.

### notification-service

Отвечает за хранение уведомлений и создание in-app уведомлений из Kafka-событий.
Сейчас использует PostgreSQL.

### payment-service

Отвечает за платежи по заказам, смену payment lifecycle статусов и публикацию
payment events.

База данных: PostgreSQL.

### admin-service

Admin-only слой поверх платформы. Собирает internal health и domain summary
из других сервисов по HTTP без прямого доступа к их базам данных и считает
derived platform analytics поверх этих summary payloads. Также агрегирует
Kafka consumer reliability config по service-level admin endpoints.

## Базы Данных

### PostgreSQL

Используется во всех реализованных сервисах:

- `auth-service`
- `user-service`
- `order-service`
- `courier-service`
- `tracking-service`
- `notification-service`
- `payment-service`

## Kafka

Kafka используется как событийная шина между сервисами.

Текущий сценарий:

1. Пользователь создает заказ в `order-service`.
2. `order-service` сохраняет заказ в PostgreSQL и пишет событие в outbox.
3. `courier-service` читает `order_created` из `orders.events` и пытается
   назначить доступного курьера.
4. `courier-service` публикует `courier_assigned` и дальнейшие
   `assignment_status_changed`.
5. `order-service` читает courier events и синхронизирует статус заказа.
6. `tracking-service` читает `orders.events` и связывает заказ с пользователем
   и курьером.
7. `notification-service` читает `orders.events` и `couriers.events`, после
   чего создает in-app уведомления.
8. `payment-service` независимо публикует payment lifecycle events в
   `payments.events`.
9. `notification-service` также читает `payments.events` и создает payment
   notifications для пользователя.
10. Если consumer исчерпал bounded retries, сообщение публикуется в service
    DLQ topic и не блокирует partition бесконечно.

## Реально Реализованные Kafka События

- `order_created`
- `order_cancelled`
- `order_status_changed`
- `delivery_started`
- `delivery_completed`
- `courier_created`
- `courier_updated`
- `courier_availability_changed`
- `courier_assigned`
- `assignment_status_changed`
- `courier_location_updated`
- `payment_created`
- `payment_confirmed`
- `payment_failed`
- `payment_refunded`

Пока только запланированы и в коде не реализованы:

- `user_registered`
- `notification_requested`
- `notification_sent`

## API Summary

### Auth Service

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`
- `PATCH /auth/users/{user_id}/role`

### User Service

- `GET /users/{user_id}`
- `PATCH /users/{user_id}`
- `GET /users/{user_id}/addresses`
- `POST /users/{user_id}/addresses`
- `PATCH /users/{user_id}/addresses/{address_id}`
- `DELETE /users/{user_id}/addresses/{address_id}`

### Order Service

- `POST /orders`
- `GET /orders/{order_id}`
- `GET /orders`
- `PATCH /orders/{order_id}/status`
- `POST /orders/{order_id}/cancel`
- `GET /orders/{order_id}/events`
- `GET /orders/admin/kafka/reliability`

### Courier Service

- `POST /couriers`
- `GET /couriers/{courier_id}`
- `PATCH /couriers/{courier_id}`
- `PATCH /couriers/{courier_id}/availability`
- `GET /couriers/available`
- `POST /couriers/assignments`
- `PATCH /couriers/assignments/{assignment_id}/status`
- `GET /couriers/{courier_id}/assignments`
- `GET /couriers/admin/kafka/reliability`

### Tracking Service

- `POST /tracking/locations`
- `GET /tracking/orders/{order_id}`
- `GET /tracking/orders/{order_id}/history`
- `GET /tracking/couriers/{courier_user_id}`
- `GET /tracking/admin/kafka/reliability`

### Notification Service

- `POST /notifications`
- `GET /notifications/{notification_id}`
- `GET /notifications/users/{user_id}`
- `PATCH /notifications/{notification_id}/read`
- `GET /notifications/admin/kafka/reliability`

### Payment Service

- `POST /payments`
- `GET /payments/{payment_id}`
- `GET /payments`
- `POST /payments/{payment_id}/confirm`
- `POST /payments/{payment_id}/fail`
- `POST /payments/{payment_id}/refund`
- `GET /payments/{payment_id}/events`

### Admin Service

- `GET /admin/overview`
- `GET /admin/services/health`
- `GET /admin/analytics`
- `GET /admin/kafka/reliability`

## Локальный Запуск

В корне проекта есть общий [docker-compose.yml](docker-compose.yml).

Он поднимает:

- Kafka
- PostgreSQL для `auth-service`
- PostgreSQL для `user-service`
- PostgreSQL для `order-service`
- PostgreSQL для `courier-service`
- PostgreSQL для `tracking-service`
- PostgreSQL для `notification-service`
- PostgreSQL для `payment-service`
- `auth-service`
- `user-service`
- `order-service`
- `courier-service`
- `tracking-service`
- `notification-service`
- `payment-service`
- `admin-service`
- `api-gateway` на порту `8080`

Запуск:

```bash
docker compose up --build
```

Для полного локального observability-режима используйте отдельный compose
override:

```bash
make observability-up
```

Он поднимает весь основной стек плюс:

- `otel-collector`
- `Prometheus` на `${PROMETHEUS_HOST_PORT:-9090}`
- `Jaeger` UI на `${JAEGER_UI_HOST_PORT:-16686}`
- `Grafana` на `${GRAFANA_HOST_PORT:-3000}`

Provisioned dashboards:

- `Delivery Platform Overview`
- `Delivery Platform Business`

Grafana по умолчанию использует логин `admin` и пароль `admin`, если не
переопределить `GRAFANA_ADMIN_USER` и `GRAFANA_ADMIN_PASSWORD` в `.env`.

Если пароль не подходит из-за старого persistent volume, см.
[observability/RUNBOOK.md](observability/RUNBOOK.md).

Чтобы остановить observability-режим целиком:

```bash
make observability-down
```

Если нужен только OTLP export без полного observability stack, задайте в `.env`
endpoint вручную. Например, для standalone service compose или локального
запуска вне Docker:

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318/v1/traces
```

Если endpoint не задан, но `OTEL_ENABLED=true`, сервисы используют console
exporter. Это удобно для локальной проверки span graph без отдельного collector.

По умолчанию root compose публикует только те host-порты, которые реально нужны
для локальной разработки и тестов:

- `api-gateway` на `${API_GATEWAY_HOST_PORT:-8080}`;
- test/local PostgreSQL для сервисов на `5433..5439`;
- Kafka на `${KAFKA_EXTERNAL_HOST_PORT:-29092}`.

`zookeeper` в root compose и `postgres/kafka/zookeeper` в service-level compose
наружу больше не публикуются: они доступны только внутри своей Docker сети. Это
убирает основную причину конфликтов между общим стеком и запуском отдельного
сервиса.

Если запускать сервисы вне Docker, сначала подготовьте общее Python-окружение
в корне репозитория. Для Python 3.12 это важно: `venv` по умолчанию не
содержит `setuptools`, а локальные editable installs в этом репозитории на него
опираются.

```bash
python -m venv .venv
source .venv/bin/activate
python -m ensurepip --upgrade
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ./libs/platform-common
python -m pip install \
  -e 'services/api-gateway[dev]' \
  -e 'services/admin-service[dev]' \
  -e 'services/auth-service[dev]' \
  -e 'services/user-service[dev]' \
  -e 'services/order-service[dev]' \
  -e 'services/courier-service[dev]' \
  -e 'services/tracking-service[dev]' \
  -e 'services/notification-service[dev]' \
  -e 'services/payment-service[dev]'
```

После этого используйте `.env.example` в корне каждого сервиса и запускайте
нужный сервис из его директории.

## Тесты

Service API tests теперь используют `PostgreSQL`, а не `SQLite`. Для локального
прогона сначала поднимите только тестовые базы:

```bash
./scripts/start-test-postgres.sh
```

Скрипт сам дожидается `healthy`-состояния всех тестовых PostgreSQL контейнеров,
поэтому дополнительная пауза перед `pytest` не нужна.

Дальше запускайте тесты из директории нужного сервиса, например:

```bash
cd services/auth-service
../../.venv/bin/python -m pytest -q
```

Тестовые базы по умолчанию:

- `auth_test` на `localhost:5435`
- `users_test` на `localhost:5436`
- `orders_test` на `localhost:5438`
- `couriers_test` на `localhost:5433`
- `notifications_test` на `localhost:5434`
- `tracking_test` на `localhost:5437`
- `payments_test` на `localhost:5439`

При необходимости любой сервисный test DB URL можно переопределить через
стандартную переменную окружения сервиса, например `AUTH_DATABASE_URL`,
`ORDER_DATABASE_URL` или `PAYMENT_DATABASE_URL`.

Быстрый workflow из корня репозитория:

```bash
make bootstrap
make install
make observability-config
make test-postgres-up
make test
make test-e2e-gateway
make lint
make mypy
make smoke-service-composes
```

`make test` теперь включает:

- root-level tests для `platform-common` tracing/observability;
- unit/service API test suites по всем реализованным сервисам;
- PostgreSQL-backed integration checks;
- cross-service Kafka contract tests из `tests/contracts/test_kafka_contracts.py`.

Kafka consumers по умолчанию используют:

- `*_KAFKA_CONSUMER_MAX_RETRIES=3`
- `*_KAFKA_CONSUMER_RETRY_BACKOFF_SECONDS=1`
- `*_KAFKA_CONSUMER_DLQ_TOPIC=<service>.dlq`

Эти переменные уже проброшены в root `docker-compose.yml` и в service-level
compose файлы для `order-service`, `courier-service`, `tracking-service`,
`notification-service`.

Для быстрой операторской проверки доступен агрегированный admin snapshot:

```bash
curl -H "Authorization: Bearer <admin-token>" \
  http://localhost:8080/admin/kafka/reliability
```

Для работы с конкретным DLQ topic локально:

```bash
python scripts/kafka-dlq-tool.py peek --topic order-service.dlq --limit 5
python scripts/kafka-dlq-tool.py replay \
  --event-file /tmp/order-dlq-event.json \
  --replayed-by local-operator \
  --reason "fixed downstream bug" \
  --dry-run
```

`peek` читает и кратко суммаризирует DLQ события, а `replay` восстанавливает
original event, добавляет replay metadata и публикует его обратно в source
topic. Для реальной публикации просто уберите `--dry-run`.

Когда test DB больше не нужны:

```bash
make test-postgres-down
```

Полный сквозной сценарий через `api-gateway`, локально поднятые сервисы и Kafka:

```bash
make test-e2e-gateway
```

Эта команда сама поднимает test PostgreSQL и Kafka, стартует сервисы локально,
проверяет внешний flow через gateway и затем останавливает инфраструктуру.

Отдельно можно прогонять только межсервисные event contracts:

```bash
make test-kafka-contracts
```

Этот набор поднимает реальные producer/consumer цепочки на тестовых PostgreSQL
схемах и проверяет совместимость payload между `order-service`,
`courier-service`, `tracking-service`, `notification-service` и
`payment-service`.

## Repository Standards

For repository-level workflow and contribution rules, see:

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [DEVELOPMENT.md](DEVELOPMENT.md)
- [SECURITY.md](SECURITY.md)

Проверка самостоятельного запуска каждого сервиса через его собственный
`docker-compose.yml`:

```bash
make smoke-service-composes
```

Эта команда последовательно поднимает каждый сервисный compose-стек, ждет
доступности `openapi.json` на host-порту и затем останавливает стек. Это
быстрый smoke-test на то, что сервисы действительно запускаются независимо.
Во standalone compose наружу публикуется только HTTP-порт самого сервиса.

Проверить итоговые UIs после `make observability-up`:

- Grafana: `http://localhost:${GRAFANA_HOST_PORT:-3000}`
- Jaeger: `http://localhost:${JAEGER_UI_HOST_PORT:-16686}`
- Prometheus: `http://localhost:${PROMETHEUS_HOST_PORT:-9090}`

Подробный локальный walkthrough для observability stack:

- [observability/RUNBOOK.md](observability/RUNBOOK.md)

## Publish-Ready Decisions

- репозиторий распространяется под лицензией `MIT`, см. [LICENSE](LICENSE);
- текущий runtime intentionally keeps only `PostgreSQL` and `Kafka`;
- `tracking-service` остается на `PostgreSQL` в текущей архитектуре;
- `Redis` и `MongoDB` не входят в текущий runtime, пока под них нет реального
  бизнес-кейса.

## Next Major Steps

- добавить защищённый operator workflow поверх DLQ replay tooling
  для ручных runbooks и аудита.
- добавить alerting rules и SLO/SLI слой поверх текущих dashboards.
