import pytest

from webhook_relay.security import SignatureError, sign, verify

SECRET = "s3cret"
BODY = b'{"a":1}'
NOW = 1_700_000_000


def check(timestamp: str | None, signature: str | None, body: bytes = BODY, now: int = NOW):
    verify(SECRET, timestamp, signature, body, tolerance_seconds=300, now=now)


def test_valid_signature_passes():
    check(str(NOW), sign(SECRET, NOW, BODY))


def test_wrong_secret_is_rejected():
    with pytest.raises(SignatureError, match="mismatch"):
        check(str(NOW), sign("other", NOW, BODY))


def test_tampered_body_is_rejected():
    with pytest.raises(SignatureError, match="mismatch"):
        check(str(NOW), sign(SECRET, NOW, BODY), body=b'{"a":2}')


def test_old_timestamp_is_rejected_even_with_a_valid_signature():
    old = NOW - 301
    with pytest.raises(SignatureError, match="window"):
        check(str(old), sign(SECRET, old, BODY))


def test_future_timestamp_is_rejected():
    future = NOW + 301
    with pytest.raises(SignatureError, match="window"):
        check(str(future), sign(SECRET, future, BODY))


def test_timestamp_is_part_of_the_signature():
    stale_signature = sign(SECRET, NOW - 10, BODY)
    with pytest.raises(SignatureError, match="mismatch"):
        check(str(NOW), stale_signature)


@pytest.mark.parametrize("timestamp,signature", [(None, "x"), ("1", None), ("", "")])
def test_missing_headers_are_rejected(timestamp, signature):
    with pytest.raises(SignatureError, match="missing"):
        check(timestamp, signature)


def test_non_numeric_timestamp_is_rejected():
    with pytest.raises(SignatureError, match="invalid timestamp"):
        check("yesterday", "sha256=00")
