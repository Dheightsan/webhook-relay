import json
import os
import time

import httpx
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from alembic import command
from webhook_relay.config import Settings
from webhook_relay.main import create_app
from webhook_relay.security import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign

ADMIN_KEY = "test-admin-key-0123456789"


def _test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.exit(
            "Set TEST_DATABASE_URL to a PostgreSQL database whose name ends in _test "
            "(it is created if missing and wiped on every run).",
            returncode=2,
        )
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        pytest.exit(f"Refusing to run: database '{name}' does not end in _test.", returncode=2)
    return url


def _ensure_database(url: str) -> None:
    parsed = make_url(url)
    admin = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": parsed.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{parsed.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _test_database_url()
    _ensure_database(url)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        cfg = Config("alembic.ini")
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    engine.dispose()
    return url


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        admin_api_key=ADMIN_KEY,
        delivery_backoff_seconds=0,
        allow_private_targets=True,
    )


@pytest.fixture
def app(settings: Settings):
    app = create_app(settings)
    app.state.deliverer.sleep = lambda _seconds: None
    yield app
    with app.state.engine.begin() as conn:
        conn.execute(text("TRUNCATE sources, events, deliveries CASCADE"))
    app.state.engine.dispose()


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def admin() -> dict[str, str]:
    return {"X-API-Key": ADMIN_KEY}


@pytest.fixture
def make_source(client, admin):
    def _make(name: str = "github", target_url: str | None = None) -> dict:
        body = {"name": name, "target_url": target_url}
        response = client.post("/sources", json=body, headers=admin)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def send_hook(client):
    def _send(source: dict, payload: dict | bytes, *, event_id: str | None = None, **overrides):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        timestamp = overrides.pop("timestamp", int(time.time()))
        headers = {
            TIMESTAMP_HEADER: str(timestamp),
            SIGNATURE_HEADER: overrides.pop("signature", sign(source["secret"], timestamp, body)),
            "Content-Type": "application/json",
        }
        if event_id:
            headers["X-Event-Id"] = event_id
        headers.update(overrides)
        return client.post(source["hook_path"], content=body, headers=headers)

    return _send


@pytest.fixture
def target(app):

    class Target:
        def __init__(self) -> None:
            self.requests: list[httpx.Request] = []
            self.responses: list[int | Exception] = []

        def handler(self, request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            outcome = self.responses.pop(0) if self.responses else 200
            if isinstance(outcome, Exception):
                raise outcome
            return httpx.Response(outcome)

    fake = Target()
    app.state.deliverer.transport = httpx.MockTransport(fake.handler)
    return fake
