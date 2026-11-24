import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from webhook_relay.db import get_db
from webhook_relay.models import PENDING, STORED, Event, Source
from webhook_relay.schemas import Accepted
from webhook_relay.security import SIGNATURE_HEADER, TIMESTAMP_HEADER, SignatureError, verify

router = APIRouter(tags=["hooks"])


async def read_body(request: Request) -> bytes:
    """Read the raw body (the signature covers the exact bytes) with a size cap."""
    limit: int = request.app.state.settings.max_body_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(413, "payload too large")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, "payload too large")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/hooks/{source_id}", response_model=Accepted, status_code=202)
def receive(
    source_id: uuid.UUID,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    body: bytes = Depends(read_body),
    timestamp: str | None = Header(default=None, alias=TIMESTAMP_HEADER),
    signature: str | None = Header(default=None, alias=SIGNATURE_HEADER),
    event_id: str | None = Header(default=None, alias="X-Event-Id", max_length=200),
    db: Session = Depends(get_db),
):
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(404, "source not found")

    settings = request.app.state.settings
    try:
        verify(source.secret, timestamp, signature, body, settings.signature_tolerance_seconds)
    except SignatureError as exc:
        raise HTTPException(401, str(exc)) from None

    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, "body is not valid JSON") from None
    if b"\\u0000" in body:
        raise HTTPException(400, "null characters are not supported")

    event = Event(
        source_id=source.id,
        external_id=event_id,
        payload=payload,
        delivery_status=PENDING if source.target_url else STORED,
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        # Same X-Event-Id sent twice: answer with the first event instead of storing another.
        db.rollback()
        existing = db.scalar(
            select(Event).where(Event.source_id == source.id, Event.external_id == event_id)
        )
        response.status_code = 200
        return Accepted(event_id=existing.id, duplicate=True)

    if source.target_url:
        background.add_task(request.app.state.deliverer.run, event.id)
    return Accepted(event_id=event.id, duplicate=False)
