"""Findings of the security review (2026-10-30), each pinned by a test. Invented people only."""

from fastapi.testclient import TestClient
from helpers import ADMIN, ADMIN_PIN, APP_HEADER, add_person, login

from app import auth, models
from app.main import app


def device():
    """Another browser: its own cookies, nothing shared with the others."""
    return TestClient(app, headers=APP_HEADER)


def wrong_pins(client, name=ADMIN, times=auth.MAX_FAILED_LOGINS):
    for _ in range(times):
        assert client.post("/api/login", json={"name": name, "pin": "0000"}).status_code == 401


def try_login(client, name=ADMIN, pin=ADMIN_PIN) -> int:
    return client.post("/api/login", json={"name": name, "pin": pin}).status_code


# 1. Anyone at home could lock every parent out with wrong PINs. A browser the person logged in with before stays usable


def test_wrong_pins_elsewhere_dont_lock_a_known_device(client):
    login(client)
    client.post("/api/logout")
    other = device()
    wrong_pins(other)
    assert try_login(other) == 429
    assert try_login(client) == 200


def test_a_known_device_gets_a_few_tries_of_its_own(client):
    login(client)
    client.post("/api/logout")
    wrong_pins(client)
    # Its wrong PINs didn't count against the person
    assert try_login(device()) == 200
    # Now it is a device like any other: its wrong PINs count, and lock the person
    wrong_pins(client)
    assert try_login(client) == 429


def test_a_device_is_known_per_person(client):
    login(client)
    add_person(client, "Lena", pin="5678")
    tablet = device()
    login(tablet, "Lena", "5678")
    tablet.post("/api/logout")
    wrong_pins(device())
    assert try_login(tablet) == 429


def test_a_correct_login_on_a_known_device_lifts_the_lock(client):
    login(client)
    client.post("/api/logout")
    wrong_pins(device())
    assert try_login(client) == 200
    assert try_login(device()) == 200


def test_the_device_cookie_stays_with_the_hub(client, monkeypatch):
    monkeypatch.setenv("COOKIE_DOMAIN", "local.example.ch")
    response = login(client)
    header = next(v for k, v in response.headers.multi_items() if k == "set-cookie" and v.startswith("hub_device="))
    # Other apps at home get the login cookie, never this one
    assert "Domain=" not in header
    assert "HttpOnly" in header and "SameSite=strict" in header


def test_known_devices_are_capped(client, db):
    for _ in range(auth.MAX_DEVICES + 5):
        login(device())
    assert db.query(models.KnownDevice).count() == auth.MAX_DEVICES


# 4. Any page on the family's domain could make a browser send the hub cookie with a change (log out everywhere)


def test_changes_need_the_app_header(client):
    login(client)
    bare = TestClient(app)
    bare.cookies.set("hub_session", client.cookies.get("hub_session"))
    refused = bare.post("/api/logout-everywhere")
    assert refused.status_code == 403 and refused.json()["detail"] == "csrf"
    assert bare.post("/api/login", json={"name": ADMIN, "pin": ADMIN_PIN}).status_code == 403
    # Reading needs no header, and the login still counts
    assert bare.get("/api/me").status_code == 200
