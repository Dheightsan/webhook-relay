import uuid

import pytest


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong-key-wrong-key-1"}])
def test_admin_routes_require_the_api_key(client, headers):
    assert client.get("/sources", headers=headers).status_code == 401
    assert client.post("/sources", json={"name": "x"}, headers=headers).status_code == 401


def test_create_returns_the_secret_once(client, admin, make_source):
    created = make_source("stripe")
    assert len(created["secret"]) == 64
    assert created["hook_path"] == f"/hooks/{created['id']}"

    listed = client.get("/sources", headers=admin).json()
    assert [s["name"] for s in listed] == ["stripe"]
    assert "secret" not in listed[0]
    assert "secret" not in client.get(f"/sources/{created['id']}", headers=admin).json()


def test_get_unknown_source_is_404(client, admin):
    assert client.get(f"/sources/{uuid.uuid4()}", headers=admin).status_code == 404


def test_name_is_required(client, admin):
    assert client.post("/sources", json={"name": ""}, headers=admin).status_code == 422


def test_target_must_be_an_http_url(client, admin):
    response = client.post(
        "/sources", json={"name": "x", "target_url": "file:///etc/passwd"}, headers=admin
    )
    assert response.status_code == 422


def test_private_targets_are_rejected_by_default(app, client, admin):
    app.state.settings.allow_private_targets = False
    for url in ("http://127.0.0.1:9000/in", "http://10.0.0.5/in", "http://169.254.169.254/latest"):
        response = client.post("/sources", json={"name": "x", "target_url": url}, headers=admin)
        assert response.status_code == 422, url
        assert "non-public" in response.json()["detail"]
