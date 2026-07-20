# payment-service

`payment-service` отвечает за платежи по заказам, хранение их статусов,
аудит событий и публикацию доменных payment events через outbox.

## Что умеет

- создавать платежи по заказу;
- получать и фильтровать список платежей;
- подтверждать, помечать failed и refund-ить платежи;
- публиковать `payment_created`, `payment_confirmed`, `payment_failed`,
  `payment_refunded` в `payments.events`;
- отдавать admin summary для `admin-service`.

## API

- `POST /payments`
- `GET /payments`
- `GET /payments/{payment_id}`
- `GET /payments/{payment_id}/events`
- `POST /payments/{payment_id}/confirm`
- `POST /payments/{payment_id}/fail`
- `POST /payments/{payment_id}/refund`
- `GET /payments/admin/summary`

## Запуск отдельно

```bash
docker compose -f services/payment-service/docker-compose.yml up --build
```
