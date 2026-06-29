import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import NotificationChannel, NotificationStatus


class NotificationCreate(BaseModel):
    user_id: uuid.UUID | None = None
    channel: NotificationChannel = NotificationChannel.IN_APP
    title: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1, max_length=4000)
    payload: dict[str, Any] = Field(default_factory=dict)


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None
    channel: NotificationChannel
    status: NotificationStatus
    title: str
    message: str
    source_event_type: str | None
    source_event_id: str | None
    aggregate_type: str | None
    aggregate_id: str | None
    payload: dict[str, Any]
    created_at: datetime
    sent_at: datetime | None
    read_at: datetime | None


class NotificationListResponse(BaseModel):
    items: list[NotificationRead]
    total: int
    limit: int
    offset: int
