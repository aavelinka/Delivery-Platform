from enum import StrEnum


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    TELEGRAM = "telegram"


class NotificationStatus(StrEnum):
    CREATED = "created"
    SENT = "sent"
    FAILED = "failed"
    READ = "read"
