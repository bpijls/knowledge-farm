import pytest

from app.config import settings
from app.routers import access as access_router
from app.services import access


@pytest.fixture
def locked(monkeypatch):
    monkeypatch.setattr(settings, "access_key", "open-sesame")


async def test_open_when_no_key_is_set(client):
    assert (await client.get("/api/session")).json() == {"required": False, "ok": True}
    assert (await client.get("/api/graphs")).status_code == 200


async def test_the_key_is_needed_for_everything_but_login(client, locked):
    assert (await client.get("/api/health")).status_code == 200
    assert (await client.get("/api/session")).json() == {"required": True, "ok": False}
    for path in ["/api/graphs", "/api/report-styles", "/api/jobs", "/api/images?spec=x",
                 "/api/graphs/stream?seeds=water"]:
        assert (await client.get(path)).status_code == 401, path
    assert (await client.delete("/api/graphs/x")).status_code == 401


async def test_wrong_key_is_refused(client, locked, monkeypatch):
    monkeypatch.setattr(access_router.asyncio, "sleep", _no_sleep)
    res = await client.post("/api/login", json={"key": "guess"})
    assert res.status_code == 401 and access.COOKIE not in res.cookies


async def test_login_sets_a_cookie_that_opens_the_api(client, locked):
    res = await client.post("/api/login", json={"key": " open-sesame "})
    assert res.status_code == 204
    cookie = res.cookies[access.COOKIE]
    assert "open-sesame" not in cookie
    assert (await client.get("/api/graphs")).status_code == 200
    assert (await client.get("/api/session")).json() == {"required": True, "ok": True}
    await client.post("/api/logout")
    client.cookies.clear()
    assert (await client.get("/api/graphs")).status_code == 401


async def test_scripts_can_send_the_key_as_a_header(client, locked):
    assert (await client.get("/api/graphs", headers={"X-Access-Key": "open-sesame"})).status_code == 200
    assert (await client.get("/api/graphs", headers={"X-Access-Key": "nope"})).status_code == 401


async def _no_sleep(_):
    return None
