from enum import StrEnum


class PaymentStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentMethod(StrEnum):
    CARD = "card"
    SBP = "sbp"
    APPLE_PAY = "apple_pay"
    GOOGLE_PAY = "google_pay"
