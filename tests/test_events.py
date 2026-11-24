import uuid

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from webhook_relay.db import Base


def test_events_are_paginated_newest_first(client, admin, make_source, send_hook):
    source = make_source()
    ids = [send_hook(source, {"n": n}).json()["event_id"] for n in range(5)]

    page = client.get(f"/sources/{source['id']}/events?limit=2", headers=admin).json()
    assert page["total"] == 5
    assert [e["id"] for e in page["items"]] == ids[::-1][:2]

    rest = client.get(f"/sources/{source['id']}/events?limit=2&offset=4", headers=admin).json()
    assert [e["id"] for e in rest["items"]] == [ids[0]]


def test_events_can_be_filtered_by_status(client, admin, make_source, send_hook, target):
    target.responses = [200, 400]
    source = make_source(target_url="http://receiver.test/in")
    send_hook(source, {"n": 1})
    send_hook(source, {"n": 2})

    def total(status: str) -> int:
        url = f"/sources/{source['id']}/events?delivery_status={status}"
        return client.get(url, headers=admin).json()["total"]

    assert (total("delivered"), total("failed"), total("pending")) == (1, 1, 0)


def test_invalid_filter_and_limits_are_422(client, admin, make_source):
    source = make_source()
    base = f"/sources/{source['id']}/events"
    assert client.get(base + "?delivery_status=nope", headers=admin).status_code == 422
    assert client.get(base + "?limit=0", headers=admin).status_code == 422
    assert client.get(base + "?limit=101", headers=admin).status_code == 422


def test_unknown_source_and_event_are_404(client, admin):
    assert client.get(f"/sources/{uuid.uuid4()}/events", headers=admin).status_code == 404
    assert client.get(f"/events/{uuid.uuid4()}", headers=admin).status_code == 404


def test_events_require_the_api_key(client, make_source, send_hook):
    source = make_source()
    event_id = send_hook(source, {}).json()["event_id"]
    assert client.get(f"/sources/{source['id']}/events").status_code == 401
    assert client.get(f"/events/{event_id}").status_code == 401


def test_migrations_match_the_models(database_url):
    engine = create_engine(database_url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == []
