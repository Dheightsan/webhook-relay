import json

import httpx

from webhook_relay.security import SIGNATURE_HEADER, TIMESTAMP_HEADER, verify

URL = "http://receiver.test/in"


def detail(client, admin, response) -> dict:
    return client.get(f"/events/{response.json()['event_id']}", headers=admin).json()


def test_event_is_forwarded_with_a_valid_signature(client, admin, make_source, send_hook, target):
    source = make_source(target_url=URL)
    response = send_hook(source, {"order": 7})

    assert detail(client, admin, response)["delivery_status"] == "delivered"
    (request,) = target.requests
    assert str(request.url) == URL
    assert json.loads(request.content) == {"order": 7}
    # The receiver can check it with the same scheme and the source secret.
    verify(
        source["secret"],
        request.headers[TIMESTAMP_HEADER],
        request.headers[SIGNATURE_HEADER],
        request.content,
        tolerance_seconds=300,
    )


def test_server_errors_are_retried_until_success(client, admin, make_source, send_hook, target):
    target.responses = [503, httpx.ConnectError("boom"), 200]
    source = make_source(target_url=URL)
    event = detail(client, admin, send_hook(source, {"a": 1}))

    assert event["delivery_status"] == "delivered"
    assert [(d["attempt"], d["ok"]) for d in event["deliveries"]] == [
        (1, False),
        (2, False),
        (3, True),
    ]
    assert event["deliveries"][0]["status_code"] == 503
    assert event["deliveries"][1]["error"] == "ConnectError"


def test_gives_up_after_the_maximum_number_of_attempts(
    client, admin, make_source, send_hook, target
):
    target.responses = [500, 500, 500, 200]
    source = make_source(target_url=URL)
    event = detail(client, admin, send_hook(source, {"a": 1}))

    assert event["delivery_status"] == "failed"
    assert len(event["deliveries"]) == 3
    assert len(target.requests) == 3


def test_client_errors_are_not_retried(client, admin, make_source, send_hook, target):
    target.responses = [400, 200]
    source = make_source(target_url=URL)
    event = detail(client, admin, send_hook(source, {"a": 1}))

    assert event["delivery_status"] == "failed"
    assert len(event["deliveries"]) == 1


def test_rate_limit_responses_are_retried(client, admin, make_source, send_hook, target):
    target.responses = [429, 200]
    source = make_source(target_url=URL)
    assert detail(client, admin, send_hook(source, {}))["delivery_status"] == "delivered"


def test_private_target_is_blocked_at_delivery_time(
    app, client, admin, make_source, send_hook, target
):
    source = make_source(target_url="http://127.0.0.1:9000/in")  # allowed while creating
    app.state.settings.allow_private_targets = False  # policy tightened afterwards
    event = detail(client, admin, send_hook(source, {"a": 1}))

    assert event["delivery_status"] == "failed"
    assert target.requests == []
    assert "non-public" in event["deliveries"][0]["error"]
    assert len(event["deliveries"]) == 1


def test_redeliver_sends_the_event_again(client, admin, make_source, send_hook, target):
    target.responses = [400]
    source = make_source(target_url=URL)
    response = send_hook(source, {"a": 1})
    event_id = response.json()["event_id"]
    assert detail(client, admin, response)["delivery_status"] == "failed"

    redelivered = client.post(f"/events/{event_id}/redeliver", headers=admin)
    assert redelivered.status_code == 202

    event = detail(client, admin, response)
    assert event["delivery_status"] == "delivered"
    assert [d["attempt"] for d in event["deliveries"]] == [1, 2]


def test_redeliver_needs_a_target(client, admin, make_source, send_hook):
    source = make_source()
    event_id = send_hook(source, {}).json()["event_id"]
    assert client.post(f"/events/{event_id}/redeliver", headers=admin).status_code == 409


def test_redeliver_requires_the_api_key(client, make_source, send_hook):
    source = make_source(target_url=URL)
    event_id = send_hook(source, {}).json()["event_id"]
    assert client.post(f"/events/{event_id}/redeliver").status_code == 401
