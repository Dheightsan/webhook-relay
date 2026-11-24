import hashlib
import hmac
import time

TIMESTAMP_HEADER = "X-Relay-Timestamp"
SIGNATURE_HEADER = "X-Relay-Signature"


class SignatureError(Exception):
    pass


def sign(secret: str, timestamp: int, body: bytes) -> str:
    message = f"{timestamp}.".encode() + body
    digest = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify(
    secret: str,
    timestamp_header: str | None,
    signature_header: str | None,
    body: bytes,
    tolerance_seconds: int,
    now: float | None = None,
) -> None:
    if not timestamp_header or not signature_header:
        raise SignatureError("missing signature headers")
    try:
        timestamp = int(timestamp_header)
    except ValueError:
        raise SignatureError("invalid timestamp") from None
    current = time.time() if now is None else now
    if abs(current - timestamp) > tolerance_seconds:
        raise SignatureError("timestamp outside the allowed window")
    expected = sign(secret, timestamp, body)
    if not hmac.compare_digest(expected, signature_header):
        raise SignatureError("signature mismatch")
