import uuid
from datetime import datetime
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    target_url: AnyHttpUrl | None = None


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    target_url: str | None
    created_at: datetime


class SourceCreated(SourceOut):
    secret: str
    hook_path: str


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attempt: int
    ok: bool
    status_code: int | None
    error: str | None
    created_at: datetime


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    external_id: str | None
    delivery_status: str
    received_at: datetime


class EventDetail(EventOut):
    payload: Any
    deliveries: list[DeliveryOut]


class EventPage(BaseModel):
    items: list[EventOut]
    total: int


class Accepted(BaseModel):
    event_id: uuid.UUID
    duplicate: bool
