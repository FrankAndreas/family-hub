"""The PIN login at home: a cookie every app at home gets; never through the Cloudflare tunnel. Invented people.
A comment above a test names the review it came from, if any."""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient
from helpers import (
    ADMIN,
    ADMIN_PIN,
    THROUGH_TUNNEL,
    all_set_cookies,
    bearer_session,
    login,
    make_person,
    set_cookie,
    signed,
)

from app import models
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
    assert client.get("/api/config").json() == {"default_language": "de", "mails": False}
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


# A login in use doesn't run out (functional review 2026-11-07): the hub's page renews it once it is a day old


def aged_login(client, db, days_left=28, manage_sid=None):
    """A login from a few days ago: tokens that run out in `days_left` days."""
    admin = models.Person.by_name(db, ADMIN)
    jti = uuid.uuid4().hex
    common = {"sub": str(admin.id), "ver": admin.token_version}
    exp = {"exp": datetime.now(timezone.utc) + timedelta(days=days_left)}
    session = signed({**common, **exp, "typ": "session", "jti": jti})
    manage = signed({**common, **exp, "typ": "manage", "sid": manage_sid or jti})
    client.cookies.set("hub_session", session)
    client.cookies.set("hub_manage", manage)
    return session, jti


def days_left(token):
    exp = jwt.decode(token, options={"verify_signature": False})["exp"]
    return (datetime.fromtimestamp(exp, timezone.utc) - datetime.now(timezone.utc)) / timedelta(days=1)


def test_a_fresh_login_isnt_renewed(client):
    login(client)
    assert all_set_cookies(client.get("/api/me")) == []


def test_a_login_in_use_is_renewed(client, db):
    old, jti = aged_login(client, db)
    response = client.get("/api/me")
    session = set_cookie(response, "hub_session").split(";")[0].split("=", 1)[1]
    manage = set_cookie(response, "hub_manage").split(";")[0].split("=", 1)[1]
    assert days_left(session) > 29.9 and days_left(manage) > 29.9
    claims = jwt.decode(session, options={"verify_signature": False})
    assert claims["jti"] == jti and jwt.decode(manage, options={"verify_signature": False})["sid"] == jti
    # Still one login: it manages, and logging out ends every copy of it
    assert client.get("/api/people").status_code == 200
    client.post("/api/logout")
    assert bearer_session(old)["valid"] is False


def test_only_the_logins_own_manage_cookie_is_renewed(client, db):
    aged_login(client, db, manage_sid="another-login")
    response = client.get("/api/me")
    assert set_cookie(response, "hub_session")
    assert not any(c.startswith("hub_manage=") for c in all_set_cookies(response))


def test_an_ended_login_isnt_renewed(client, db):
    old, _ = aged_login(client, db)
    client.post("/api/logout")
    client.cookies.set("hub_session", old)
    response = client.get("/api/me")
    assert response.status_code == 401 and all_set_cookies(response) == []
