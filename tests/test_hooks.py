import time
import uuid

from webhook_relay.security import SIGNATURE_HEADER, TIMESTAMP_HEADER


def events_of(client, admin, source) -> dict:
    return client.get(f"/sources/{source['id']}/events", headers=admin).json()


def test_signed_webhook_is_accepted_and_stored(client, admin, make_source, send_hook):
    source = make_source()
    response = send_hook(source, {"action": "opened", "n": 1})

    assert response.status_code == 202
    assert response.json()["duplicate"] is False
    event = client.get(f"/events/{response.json()['event_id']}", headers=admin).json()
    assert event["payload"] == {"action": "opened", "n": 1}
    assert event["delivery_status"] == "stored"


def test_bad_signature_is_rejected_and_nothing_is_stored(client, admin, make_source, send_hook):
    source = make_source()
    response = send_hook(source, {"a": 1}, signature="sha256=" + "0" * 64)

    assert response.status_code == 401
    assert events_of(client, admin, source)["total"] == 0


def test_signature_from_another_source_is_rejected(client, admin, make_source, send_hook):
    one, two = make_source("one"), make_source("two")
    body = b'{"a":1}'
    from webhook_relay.security import sign

    stamp = int(time.time())
    response = send_hook(two, body, signature=sign(one["secret"], stamp, body), timestamp=stamp)
    assert response.status_code == 401


def test_replayed_request_with_old_timestamp_is_rejected(client, make_source, send_hook):
    source = make_source()
    from webhook_relay.security import sign

    old = int(time.time()) - 3600
    body = b'{"a":1}'
    response = send_hook(source, body, timestamp=old, signature=sign(source["secret"], old, body))
    assert response.status_code == 401


def test_missing_signature_headers_are_rejected(client, make_source):
    source = make_source()
    response = client.post(source["hook_path"], json={"a": 1})
    assert response.status_code == 401


def test_unknown_source_is_404(client):
    response = client.post(
        f"/hooks/{uuid.uuid4()}",
        json={},
        headers={TIMESTAMP_HEADER: "1", SIGNATURE_HEADER: "sha256=00"},
    )
    assert response.status_code == 404


def test_signed_but_not_json_is_400(make_source, send_hook):
    source = make_source()
    assert send_hook(source, b"not json").status_code == 400


def test_null_character_in_payload_is_400(make_source, send_hook):
    source = make_source()
    assert send_hook(source, b'{"a":"\\u0000"}').status_code == 400


def test_oversized_body_is_413(app, make_source, send_hook):
    app.state.settings.max_body_bytes = 50
    source = make_source()
    assert send_hook(source, {"blob": "x" * 200}).status_code == 413


def test_repeated_event_id_is_stored_once(client, admin, make_source, send_hook):
    source = make_source()
    first = send_hook(source, {"n": 1}, event_id="evt_1")
    second = send_hook(source, {"n": 1}, event_id="evt_1")

    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json() == {"event_id": first.json()["event_id"], "duplicate": True}
    assert events_of(client, admin, source)["total"] == 1


def test_same_event_id_on_different_sources_is_not_a_duplicate(make_source, send_hook):
    one, two = make_source("one"), make_source("two")
    assert send_hook(one, {}, event_id="evt_1").status_code == 202
    assert send_hook(two, {}, event_id="evt_1").status_code == 202
