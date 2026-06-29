# Delivery Platform

## Current implementation status

Implemented services:

- `api-gateway` on port `8080`
- `auth-service` internally on port `8000`
- `order-service` internally on port `8000`
- `courier-service` internally on port `8000`
- `notification-service` internally on port `8000`
- `user-service` internally on port `8000`
- `tracking-service` internally on port `8000`

Before running `docker compose up --build`, create a local `.env` from `.env.example`
and set `JWT_SECRET_KEY` plus `GATEWAY_INTERNAL_SECRET`.

In the root Docker Compose setup, external clients should call only `api-gateway`
on port `8080`. The application services are reachable inside the Compose network
and trust identity headers signed with `GATEWAY_INTERNAL_SECRET`.

Identity rule:

- `courier-service` keeps its internal courier profile id as `courier_id`.
- Cross-service order and tracking APIs use `courier_user_id`, the auth-service user id
  from the JWT subject.
- Tracking learns order owners from `orders.events`; order tracking reads are limited
  to that customer, the assigned courier, or an admin.

Микросервисная backend-платформа для управления доставкой еды и посылок.

Проект строится как учебно-практическая система, похожая на реальный backend сервиса доставки: клиент создает заказ, система назначает курьера, заказ проходит по статусам, курьер отправляет геопозицию, а пользователь получает уведомления.

## Цель проекта

Создать надежный микросервисный backend на Python с событийной архитектурой через Kafka.

Основные возможности:

- регистрация и авторизация пользователей;
- управление профилями и адресами;
- создание и отслеживание заказов;
- назначение курьеров;
- обновление статусов доставки;
- хранение истории событий;
- отправка уведомлений;
- дальнейшее подключение платежей и админ-панели.

## Технологический стек

- Python 3.12
- FastAPI
- Pydantic v2
- SQLAlchemy 2.0
- Alembic
- PostgreSQL
- MongoDB
- Kafka
- Redis
- Docker
- Docker Compose
- pytest
- Ruff
- mypy
- OpenTelemetry

## Архитектурный подход

Система делится на независимые сервисы. Каждый сервис владеет своими данными и не ходит напрямую в базу другого сервиса.

Основной обмен между сервисами происходит через Kafka-события.

Синхронные HTTP-вызовы используются только там, где это действительно нужно для API-запроса.

## Сервисы

### api-gateway

Единая точка входа для внешних клиентов: мобильного приложения, web-клиента, админки и клиентской панели.

На старте можно не реализовывать как отдельный сервис, а обращаться к сервисам напрямую через Docker Compose. Позже gateway можно добавить для маршрутизации, авторизации и rate limiting.

### auth-service

Отвечает за регистрацию, логин, JWT-токены, refresh-токены и роли.

База данных: PostgreSQL.

### user-service

Отвечает за пользовательские профили, адреса доставки и контактные данные.

База данных: PostgreSQL.

### order-service

Центральный сервис системы. Отвечает за создание заказов, хранение статусов, отмену заказов и историю изменений.

База данных: PostgreSQL.

### courier-service

Отвечает за курьеров, их доступность, назначение на заказы и список заданий.

База данных: PostgreSQL.

### tracking-service

Отвечает за текущую геолокацию курьера и историю перемещений по заказу.

База данных: MongoDB.

MongoDB подходит для tracking-сервиса, потому что геолокационные события могут приходить часто, иметь гибкую структуру и храниться как документы.

### notification-service

Отвечает за создание, отправку и хранение уведомлений.

База данных: PostgreSQL или MongoDB.

Для MVP можно использовать PostgreSQL. Если понадобится хранить гибкие шаблоны, payload и сырую историю доставок уведомлений, можно перенести часть данных в MongoDB.

### payment-service

Отвечает за платежи, подтверждения, ошибки оплаты и возвраты.

База данных: PostgreSQL.

Этот сервис лучше добавить после базового MVP.

### admin-service

Отвечает за инструменты диспетчера: просмотр заказов, ручное назначение курьера, просмотр пользователей, курьеров и системных событий.

Этот сервис лучше добавить после базового MVP.

## Базы данных

### PostgreSQL

Используется для строгих транзакционных данных:

- пользователи;
- авторизация;
- адреса;
- заказы;
- курьеры;
- платежи;
- статусы;
- назначения.

### MongoDB

Используется для гибких и часто изменяющихся документов:

- история геолокации;
- tracking events;
- сырые Kafka-события;
- логи уведомлений;
- дополнительные metadata.

### Redis

Используется для быстрых временных данных:

- кеш;
- rate limiting;
- временные блокировки;
- idempotency keys;
- короткоживущие сессии или verification codes.

## Kafka

Kafka используется как событийная шина между сервисами.

Пример потока:

1. Клиент создает заказ в `order-service`.
2. `order-service` сохраняет заказ в PostgreSQL.
3. `order-service` публикует событие `order_created`.
4. `courier-service` получает событие и ищет доступного курьера.
5. `courier-service` публикует `courier_assigned`.
6. `notification-service` получает событие и отправляет уведомление.
7. `tracking-service` начинает принимать геолокацию по заказу.

## Kafka-события

Минимальный набор событий:

- `user_registered`
- `order_created`
- `order_cancelled`
- `order_status_changed`
- `courier_assigned`
- `courier_availability_changed`
- `courier_location_updated`
- `delivery_started`
- `delivery_completed`
- `notification_requested`
- `notification_sent`
- `payment_confirmed`
- `payment_failed`

## Endpoint'ы

### Auth Service

#### `POST /auth/register`

Регистрация пользователя.

#### `POST /auth/login`

Логин пользователя и выдача access/refresh token.

#### `POST /auth/refresh`

Обновление access token.

#### `POST /auth/logout`

Выход из аккаунта.

#### `GET /auth/me`

Получение информации о текущем авторизованном пользователе.

### User Service

#### `GET /users/{user_id}`

Получить профиль пользователя.

#### `PATCH /users/{user_id}`

Обновить профиль пользователя.

#### `GET /users/{user_id}/addresses`

Получить список адресов пользователя.

#### `POST /users/{user_id}/addresses`

Добавить адрес доставки.

#### `PATCH /users/{user_id}/addresses/{address_id}`

Обновить адрес доставки.

#### `DELETE /users/{user_id}/addresses/{address_id}`

Удалить адрес доставки.

### Order Service

#### `POST /orders`

Создать заказ.

После создания заказа сервис публикует Kafka-событие `order_created`.

#### `GET /orders/{order_id}`

Получить заказ по идентификатору.

#### `GET /orders`

Получить список заказов.

Фильтры:

- `status`;
- `user_id`;
- `courier_id`;
- `created_from`;
- `created_to`.

#### `PATCH /orders/{order_id}/status`

Изменить статус заказа.

После изменения статуса сервис публикует Kafka-событие `order_status_changed`.

#### `POST /orders/{order_id}/cancel`

Отменить заказ.

После отмены сервис публикует Kafka-событие `order_cancelled`.

#### `GET /orders/{order_id}/events`

Получить историю событий заказа.

### Courier Service

#### `POST /couriers`

Создать профиль курьера.

#### `GET /couriers/{courier_id}`

Получить данные курьера.

#### `PATCH /couriers/{courier_id}`

Обновить данные курьера.

#### `PATCH /couriers/{courier_id}/availability`

Изменить доступность курьера.

Возможные статусы:

- `online`;
- `offline`;
- `busy`.

После изменения доступности сервис публикует Kafka-событие `courier_availability_changed`.

#### `GET /couriers/available`

Получить список доступных курьеров.

#### `POST /couriers/assignments`

Назначить курьера на заказ.

После назначения сервис публикует Kafka-событие `courier_assigned`.

#### `GET /couriers/{courier_id}/assignments`

Получить список заданий курьера.

### Tracking Service

#### `POST /tracking/locations`

Сохранить текущую геопозицию курьера.

После сохранения сервис публикует Kafka-событие `courier_location_updated`.

#### `GET /tracking/orders/{order_id}`

Получить текущую позицию доставки по заказу.

#### `GET /tracking/orders/{order_id}/history`

Получить историю перемещений по заказу.

#### `GET /tracking/couriers/{courier_user_id}`

Получить текущую позицию курьера.

### Notification Service

#### `POST /notifications`

Создать уведомление вручную или по запросу другого сервиса.

#### `GET /notifications/{notification_id}`

Получить уведомление по идентификатору.

#### `GET /notifications/users/{user_id}`

Получить историю уведомлений пользователя.

#### `PATCH /notifications/{notification_id}/read`

Отметить уведомление как прочитанное.

### Payment Service

Платежный сервис добавляется после MVP.

#### `POST /payments`

Создать платеж.

#### `GET /payments/{payment_id}`

Получить платеж по идентификатору.

#### `POST /payments/{payment_id}/confirm`

Подтвердить платеж.

После подтверждения сервис публикует Kafka-событие `payment_confirmed`.

#### `POST /payments/{payment_id}/refund`

Создать возврат.

#### `GET /payments/orders/{order_id}`

Получить платежи по заказу.

### Admin Service

Админский сервис добавляется после MVP.

#### `GET /admin/orders`

Получить все заказы для диспетчера.

#### `PATCH /admin/orders/{order_id}/assign-courier`

Назначить курьера вручную.

#### `GET /admin/couriers`

Получить список всех курьеров.

#### `GET /admin/users`

Получить список всех пользователей.

#### `GET /admin/events`

Получить системные события.

## MVP

Первый этап разработки:

1. `order-service`
2. `courier-service`
3. `notification-service`
4. `auth-service`
5. `user-service`

Минимальный рабочий сценарий:

1. Пользователь регистрируется.
2. Пользователь создает заказ.
3. Заказ сохраняется в `order-service`.
4. `order-service` отправляет событие `order_created`.
5. `courier-service` назначает курьера.
6. `courier-service` отправляет событие `courier_assigned`.
7. `notification-service` отправляет уведомление пользователю.
8. Курьер меняет статус доставки.
9. Пользователь видит новый статус заказа.

## С чего начинать разработку

Первым сервисом стоит реализовать `order-service`, потому что он является центром бизнес-логики.

Минимальная первая версия `order-service`:

- модель `Order`;
- миграции Alembic;
- `POST /orders`;
- `GET /orders/{order_id}`;
- `PATCH /orders/{order_id}/status`;
- публикация `order_created` в Kafka;
- публикация `order_status_changed` в Kafka;
- базовые тесты через pytest.

## Order Service

Готовый каркас первого сервиса лежит здесь:

- [services/order-service/README.md](services/order-service/README.md)
- [services/order-service/app/main.py](services/order-service/app/main.py)

## Courier Service

Каркас второго сервиса:

- [services/courier-service/README.md](services/courier-service/README.md)
- [services/courier-service/app/main.py](services/courier-service/app/main.py)

## Notification Service

Каркас сервиса уведомлений:

- [services/notification-service/README.md](services/notification-service/README.md)
- [services/notification-service/app/main.py](services/notification-service/app/main.py)

`notification-service` слушает Kafka topics:

- `orders.events`
- `couriers.events`

На основе событий сервис создает записи в таблице `notifications`.

## Auth Service

Каркас сервиса авторизации:

- [services/auth-service/README.md](services/auth-service/README.md)
- [services/auth-service/app/main.py](services/auth-service/app/main.py)

`auth-service` отвечает за регистрацию, логин, refresh tokens, logout и `/auth/me`.

## Локальный запуск всей системы

В корне проекта есть общий [docker-compose.yml](docker-compose.yml).

Он поднимает:

- Kafka;
- Redis;
- PostgreSQL для `order-service`;
- PostgreSQL для `courier-service`;
- PostgreSQL для `notification-service`;
- PostgreSQL для `auth-service`;
- `order-service` на порту `8000`;
- `courier-service` на порту `8001`;
- `notification-service` на порту `8002`.
- `auth-service` на порту `8003`.

Запуск:

```bash
docker compose up --build
```

## Event Flow

Основной межсервисный сценарий:

1. `order-service` создает заказ и публикует `order_created` в `orders.events`.
2. `courier-service` слушает `orders.events`, получает `order_created`, ищет доступного курьера и создает assignment.
3. `courier-service` публикует `courier_assigned` в `couriers.events`.
4. `order-service` слушает `couriers.events`, получает `courier_assigned` и обновляет заказ до статуса `courier_assigned`.
5. `notification-service` слушает `orders.events` и `couriers.events`, затем создает уведомления.
