import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from webhook_relay.auth import require_admin
from webhook_relay.db import get_db
from webhook_relay.models import Source
from webhook_relay.netguard import TargetNotAllowed, check_target
from webhook_relay.schemas import SourceCreate, SourceCreated, SourceOut

router = APIRouter(prefix="/sources", tags=["sources"], dependencies=[Depends(require_admin)])


@router.post("", response_model=SourceCreated, status_code=status.HTTP_201_CREATED)
def create_source(body: SourceCreate, request: Request, db: Session = Depends(get_db)):
    target = str(body.target_url) if body.target_url else None
    if target:
        try:
            check_target(target, request.app.state.settings.allow_private_targets)
        except TargetNotAllowed as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    source = Source(name=body.name, target_url=target)
    db.add(source)
    db.commit()
    return SourceCreated(
        **SourceOut.model_validate(source).model_dump(),
        secret=source.secret,
        hook_path=f"/hooks/{source.id}",
    )


@router.get("", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db)):
    return db.scalars(select(Source).order_by(Source.created_at, Source.id)).all()


@router.get("/{source_id}", response_model=SourceOut)
def get_source(source_id: uuid.UUID, db: Session = Depends(get_db)):
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")
    return source
