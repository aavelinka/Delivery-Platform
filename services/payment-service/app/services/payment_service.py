import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from platform_common.outbox import add_outbox_event
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import OutboxEvent, Payment, PaymentEvent
from app.domain.enums import PaymentStatus
from app.kafka.events import build_event_message
from app.schemas.payments import PaymentConfirm, PaymentCreate, PaymentFail, PaymentRefund

ACTIVE_PAYMENT_STATUSES = (PaymentStatus.PENDING, PaymentStatus.CONFIRMED)


def _json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def payment_payload(payment: Payment) -> dict[str, Any]:
    return {
        "payment_id": str(payment.id),
        "order_id": str(payment.order_id),
        "user_id": str(payment.user_id),
        "amount": str(payment.amount),
        "currency": payment.currency,
        "status": payment.status.value,
        "payment_method": payment.payment_method.value,
        "provider_reference": payment.provider_reference,
        "description": payment.description,
        "failure_reason": payment.failure_reason,
        "created_at": payment.created_at.isoformat(),
        "updated_at": payment.updated_at.isoformat(),
        "confirmed_at": payment.confirmed_at.isoformat() if payment.confirmed_at else None,
        "failed_at": payment.failed_at.isoformat() if payment.failed_at else None,
        "refunded_at": payment.refunded_at.isoformat() if payment.refunded_at else None,
    }


class PaymentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_payment(self, data: PaymentCreate) -> tuple[Payment, PaymentEvent]:
        existing_payment = self.db.scalar(
            select(Payment).where(
                Payment.order_id == data.order_id,
                Payment.status.in_(ACTIVE_PAYMENT_STATUSES),
            )
        )
        if existing_payment is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Active payment for this order already exists",
            )

        payment = Payment(
            order_id=data.order_id,
            user_id=data.user_id,
            amount=data.amount,
            currency=data.currency,
            status=PaymentStatus.PENDING,
            payment_method=data.payment_method,
            description=data.description,
        )
        self.db.add(payment)
        self.db.flush()

        event = self._add_event(
            payment=payment,
            event_type="payment_created",
            previous_status=None,
            new_status=payment.status,
            payload=payment_payload(payment),
        )
        self._add_outbox_event(payment, event)

        self.db.commit()
        self.db.refresh(payment)
        self.db.refresh(event)
        return payment, event

    def get_payment(self, payment_id: uuid.UUID) -> Payment:
        payment = self.db.get(Payment, payment_id)
        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found",
            )
        return payment

    def list_payments(
        self,
        *,
        status_filter: PaymentStatus | None,
        user_id: uuid.UUID | None,
        order_id: uuid.UUID | None,
        created_from: datetime | None,
        created_to: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Payment], int]:
        query: Select[tuple[Payment]] = select(Payment)
        count_query = select(func.count()).select_from(Payment)

        filters = []
        if status_filter is not None:
            filters.append(Payment.status == status_filter)
        if user_id is not None:
            filters.append(Payment.user_id == user_id)
        if order_id is not None:
            filters.append(Payment.order_id == order_id)
        if created_from is not None:
            filters.append(Payment.created_at >= created_from)
        if created_to is not None:
            filters.append(Payment.created_at <= created_to)

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        total = self.db.scalar(count_query) or 0
        items = self.db.scalars(
            query.order_by(Payment.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return list(items), total

    def get_admin_summary(self) -> dict[str, int | Decimal | dict[str, int]]:
        total_payments = self.db.scalar(select(func.count()).select_from(Payment)) or 0
        pending_payments = self._count_by_status(PaymentStatus.PENDING)
        confirmed_payments = self._count_by_status(PaymentStatus.CONFIRMED)
        failed_payments = self._count_by_status(PaymentStatus.FAILED)
        refunded_payments = self._count_by_status(PaymentStatus.REFUNDED)
        total_amount = (
            self.db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)))
            or Decimal("0")
        )
        confirmed_amount = (
            self.db.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.status == PaymentStatus.CONFIRMED
                )
            )
            or Decimal("0")
        )
        refunded_amount = (
            self.db.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.status == PaymentStatus.REFUNDED
                )
            )
            or Decimal("0")
        )
        status_rows = self.db.execute(
            select(Payment.status, func.count()).group_by(Payment.status)
        ).all()
        payments_by_status = {
            str(status.value if isinstance(status, PaymentStatus) else status): count
            for status, count in status_rows
        }
        return {
            "total_payments": total_payments,
            "pending_payments": pending_payments,
            "confirmed_payments": confirmed_payments,
            "failed_payments": failed_payments,
            "refunded_payments": refunded_payments,
            "total_amount": total_amount,
            "confirmed_amount": confirmed_amount,
            "refunded_amount": refunded_amount,
            "payments_by_status": payments_by_status,
        }

    def confirm_payment(
        self,
        payment_id: uuid.UUID,
        data: PaymentConfirm,
    ) -> tuple[Payment, PaymentEvent]:
        payment = self.get_payment(payment_id)
        if payment.status != PaymentStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only pending payments can be confirmed",
            )

        previous_status = payment.status
        payment.status = PaymentStatus.CONFIRMED
        payment.provider_reference = data.provider_reference or payment.provider_reference
        payment.failure_reason = None
        payment.confirmed_at = datetime.now(UTC)
        payment.updated_at = payment.confirmed_at

        event = self._add_event(
            payment=payment,
            event_type="payment_confirmed",
            previous_status=previous_status,
            new_status=payment.status,
            changed_by=data.changed_by,
            payload=payment_payload(payment),
        )
        self._add_outbox_event(payment, event)

        self.db.commit()
        self.db.refresh(payment)
        self.db.refresh(event)
        return payment, event

    def fail_payment(
        self,
        payment_id: uuid.UUID,
        data: PaymentFail,
    ) -> tuple[Payment, PaymentEvent]:
        payment = self.get_payment(payment_id)
        if payment.status != PaymentStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only pending payments can be failed",
            )

        previous_status = payment.status
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = data.reason
        payment.failed_at = datetime.now(UTC)
        payment.updated_at = payment.failed_at

        payload = payment_payload(payment)
        payload["reason"] = data.reason
        event = self._add_event(
            payment=payment,
            event_type="payment_failed",
            previous_status=previous_status,
            new_status=payment.status,
            changed_by=data.changed_by,
            payload=payload,
        )
        self._add_outbox_event(payment, event)

        self.db.commit()
        self.db.refresh(payment)
        self.db.refresh(event)
        return payment, event

    def refund_payment(
        self,
        payment_id: uuid.UUID,
        data: PaymentRefund,
    ) -> tuple[Payment, PaymentEvent]:
        payment = self.get_payment(payment_id)
        if payment.status != PaymentStatus.CONFIRMED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only confirmed payments can be refunded",
            )

        previous_status = payment.status
        payment.status = PaymentStatus.REFUNDED
        payment.failure_reason = data.reason
        payment.refunded_at = datetime.now(UTC)
        payment.updated_at = payment.refunded_at

        payload = payment_payload(payment)
        payload["reason"] = data.reason
        event = self._add_event(
            payment=payment,
            event_type="payment_refunded",
            previous_status=previous_status,
            new_status=payment.status,
            changed_by=data.changed_by,
            payload=payload,
        )
        self._add_outbox_event(payment, event)

        self.db.commit()
        self.db.refresh(payment)
        self.db.refresh(event)
        return payment, event

    def list_events(self, payment_id: uuid.UUID) -> list[PaymentEvent]:
        self.get_payment(payment_id)
        items = self.db.scalars(
            select(PaymentEvent)
            .where(PaymentEvent.payment_id == payment_id)
            .order_by(PaymentEvent.created_at)
        ).all()
        return list(items)

    def _count_by_status(self, payment_status: PaymentStatus) -> int:
        return (
            self.db.scalar(
                select(func.count()).select_from(Payment).where(Payment.status == payment_status)
            )
            or 0
        )

    def _add_event(
        self,
        *,
        payment: Payment,
        event_type: str,
        previous_status: PaymentStatus | None,
        new_status: PaymentStatus | None,
        changed_by: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> PaymentEvent:
        event = PaymentEvent(
            payment_id=payment.id,
            event_type=event_type,
            previous_status=previous_status,
            new_status=new_status,
            changed_by=changed_by,
            payload=_json_safe(payload or payment_payload(payment)),
        )
        self.db.add(event)
        self.db.flush()
        return event

    def _add_outbox_event(self, payment: Payment, event: PaymentEvent) -> OutboxEvent:
        settings = get_settings()
        return add_outbox_event(
            self.db,
            OutboxEvent,
            topic=settings.kafka_payments_topic,
            payload=build_event_message(payment, event),
        )
