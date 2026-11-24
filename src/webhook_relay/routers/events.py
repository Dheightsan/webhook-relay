import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from webhook_relay.auth import require_admin
from webhook_relay.db import get_db
from webhook_relay.models import PENDING, Event, Source
from webhook_relay.schemas import EventDetail, EventOut, EventPage

router = APIRouter(tags=["events"], dependencies=[Depends(require_admin)])


@router.get("/sources/{source_id}/events", response_model=EventPage)
def list_events(
    source_id: uuid.UUID,
    delivery_status: Literal["stored", "pending", "delivered", "failed"] | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if db.get(Source, source_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")
    query = select(Event).where(Event.source_id == source_id)
    if delivery_status:
        query = query.where(Event.delivery_status == delivery_status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(
        query.order_by(Event.received_at.desc(), Event.id).limit(limit).offset(offset)
    ).all()
    return EventPage(items=[EventOut.model_validate(item) for item in items], total=total)


@router.get("/events/{event_id}", response_model=EventDetail)
def get_event(event_id: uuid.UUID, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    return event


@router.post("/events/{event_id}/redeliver", response_model=EventOut, status_code=202)
def redeliver(
    event_id: uuid.UUID,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    if not event.source.target_url:
        raise HTTPException(status.HTTP_409_CONFLICT, "source has no target_url")
    event.delivery_status = PENDING
    db.commit()
    background.add_task(request.app.state.deliverer.run, event.id)
    return event
