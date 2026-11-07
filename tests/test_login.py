"""The PIN login at home: a cookie every app at home gets; never through the Cloudflare tunnel. Invented people.
A comment above a test names the review it came from, if any."""

from datetime import timedelta

from fastapi.testclient import TestClient
from helpers import ADMIN, ADMIN_PIN, THROUGH_TUNNEL, login, make_person, set_cookie

from app.main import app


def test_login_sets_the_cookie(client, configure):
    configure(COOKIE_DOMAIN="local.example.ch")
    response = login(client)
    header = set_cookie(response, "hub_session")
    assert "HttpOnly" in header and "SameSite=lax" in header and "Domain=local.example.ch" in header
    assert f"Max-Age={int(timedelta(days=30).total_seconds())}" in header
    # Tests talk plain http (COOKIE_INSECURE=1); on the NAS the cookie is Secure
    assert "Secure" not in header
    configure(COOKIE_INSECURE=None)
    assert "Secure" in set_cookie(login(client), "hub_session")


def test_me_after_login(client):
    assert client.get("/api/me").status_code == 401
    login(client)
    me = client.get("/api/me").json()
    assert (me["name"], me["role"], me["language"]) == ("Admin", "PARENT", "de")


def test_inactive_person_cant_log_in(client, db):
    make_person(db, "Lena", active=False)
    assert client.post("/api/login", json={"name": "Lena", "pin": "5678"}).status_code == 401


def test_through_the_tunnel_no_pin_login_and_no_cookie(client):
    response = client.post("/api/login", json={"name": "Admin", "pin": ADMIN_PIN}, headers=THROUGH_TUNNEL)
    assert response.status_code == 403 and response.json()["detail"] == "login_at_home_only"
    login(client)
    # A home cookie sent to an outside address counts for nothing
    assert client.get("/api/me", headers=THROUGH_TUNNEL).status_code == 401
    assert client.get("/api/people/public", headers=THROUGH_TUNNEL).status_code == 403


def test_names_for_the_login_screen(client, db):
    make_person(db, "Lena", color="#f59e0b")
    make_person(db, "Tim", active=False)
    found = client.get("/api/people/public").json()
    assert found == [{"name": "Admin", "color": None}, {"name": "Lena", "color": "#f59e0b"}]


def test_config_for_the_login_screen(client, configure):
    assert client.get("/api/config").json() == {"default_language": "de", "pin_reset": False}
    configure(DEFAULT_LANGUAGE="en")
    assert client.get("/api/config").json()["default_language"] == "en"


# Security review 2026-10-30, finding 4: any page on the family's domain could make a browser send the hub cookie
# with a change
def test_changes_need_the_app_header(client):
    login(client)
    bare = TestClient(app)
    bare.cookies.set("hub_session", client.cookies.get("hub_session"))
    refused = bare.post("/api/logout-everywhere")
    assert refused.status_code == 403 and refused.json()["detail"] == "csrf"
    assert bare.post("/api/login", json={"name": ADMIN, "pin": ADMIN_PIN}).status_code == 403
    # Reading needs no header, and the login still counts
    assert bare.get("/api/me").status_code == 200
