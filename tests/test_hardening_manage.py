"""Managing the hub needs a cookie only the hub gets (spec 2026-10-30 hub hardening, part 1). Invented people."""

from fastapi.testclient import TestClient
from helpers import ADMIN_PIN, APP_HEADER, login, make_person
from test_cloudflare import access, outside, token  # noqa: F401

from app import auth
from app.main import app


def device():
    return TestClient(app, headers=APP_HEADER)


def manage_cookie_header(response) -> str:
    return next(v for k, v in response.headers.multi_items() if k == "set-cookie" and v.startswith("hub_manage="))


def test_session_cookie_alone_cant_manage(client):
    login(client)
    client.cookies.delete(auth.MANAGE_COOKIE, domain="testserver.local", path="/api")
    assert client.cookies.get(auth.MANAGE_COOKIE) is None
    refused = client.get("/api/people")
    assert refused.status_code == 403 and refused.json()["detail"] == "login_again"
    assert client.patch("/api/me", json={"color": "#112233"}).status_code == 403
    assert client.get("/api/me").status_code == 200
    assert client.get("/api/tiles").status_code == 200


def test_manage_cookie_of_another_login_is_refused(client):
    first, second = device(), device()
    login(first)
    login(second)
    mixed = device()
    mixed.cookies.set("hub_session", first.cookies.get("hub_session"))
    mixed.cookies.set(auth.MANAGE_COOKIE, second.cookies.get(auth.MANAGE_COOKIE), path="/api")
    refused = mixed.get("/api/people")
    assert refused.status_code == 403 and refused.json()["detail"] == "login_again"


def test_manage_cookie_flags(client, monkeypatch):
    monkeypatch.setenv("COOKIE_DOMAIN", "local.example.ch")
    header = manage_cookie_header(login(client))
    assert "Domain=" not in header
    assert "HttpOnly" in header and "SameSite=strict" in header and "Path=/api" in header


def test_own_pin_change_keeps_managing(client):
    login(client)
    assert client.put("/api/me/pin", json={"old_pin": ADMIN_PIN, "pin": "1357"}).status_code == 200
    assert client.get("/api/people").status_code == 200


def test_outside_can_still_change_own_colour(client, db, access):  # noqa: F811
    make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    response = client.patch("/api/me", json={"color": "#112233"}, headers=outside(token()))
    assert response.status_code == 200
