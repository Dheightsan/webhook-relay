import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from webhook_relay.config import Settings
from webhook_relay.models import DELIVERED, FAILED, PENDING, Delivery, Event
from webhook_relay.netguard import TargetNotAllowed, check_target
from webhook_relay.security import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign

RETRYABLE_STATUS = {408, 425, 429}


@dataclass
class Outcome:
    ok: bool
    status_code: int | None = None
    error: str | None = None
    retry: bool = False


class Deliverer:
    """Forwards stored events to their source's target URL, signed and with retries.

    Retries run inside the web process (FastAPI background tasks) and are not
    durable: a restart drops attempts that were waiting. Events left in
    `pending` can be re-sent with the redeliver endpoint.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.transport = transport
        self.sleep = sleep

    def run(self, event_id: uuid.UUID) -> None:
        for number in range(1, self.settings.delivery_max_attempts + 1):
            with self.session_factory() as db:
                event = db.get(Event, event_id)
                if event is None or not event.source.target_url:
                    return
                attempt = (
                    db.scalar(
                        select(func.count())
                        .select_from(Delivery)
                        .where(Delivery.event_id == event_id)
                    )
                    + 1
                )
                outcome = self._send(event, attempt)
                db.add(
                    Delivery(
                        event_id=event_id,
                        attempt=attempt,
                        ok=outcome.ok,
                        status_code=outcome.status_code,
                        error=outcome.error,
                    )
                )
                last = number == self.settings.delivery_max_attempts
                if outcome.ok:
                    event.delivery_status = DELIVERED
                elif not outcome.retry or last:
                    event.delivery_status = FAILED
                else:
                    event.delivery_status = PENDING
                db.commit()
                if event.delivery_status != PENDING:
                    return
            self.sleep(self.settings.delivery_backoff_seconds * 2 ** (number - 1))

    def _send(self, event: Event, attempt: int) -> Outcome:
        source = event.source
        try:
            check_target(source.target_url, self.settings.allow_private_targets)
        except TargetNotAllowed as exc:
            return Outcome(ok=False, error=str(exc))

        body = json.dumps(event.payload, separators=(",", ":"), ensure_ascii=False).encode()
        timestamp = int(time.time())
        headers = {
            "Content-Type": "application/json",
            TIMESTAMP_HEADER: str(timestamp),
            SIGNATURE_HEADER: sign(source.secret, timestamp, body),
            "X-Relay-Event-Id": str(event.id),
            "X-Relay-Delivery-Attempt": str(attempt),
        }
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=self.settings.delivery_timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = client.post(source.target_url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            return Outcome(ok=False, error=f"{type(exc).__name__}", retry=True)

        code = response.status_code
        if 200 <= code < 300:
            return Outcome(ok=True, status_code=code)
        retry = code >= 500 or code in RETRYABLE_STATUS
        return Outcome(ok=False, status_code=code, retry=retry)
