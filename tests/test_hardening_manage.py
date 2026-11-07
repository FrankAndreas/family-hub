"""Managing the hub needs a cookie only the hub gets (spec 2026-10-30 hub hardening, part 1). Invented people."""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient
from helpers import ADMIN_PIN, APP_HEADER, login, make_person
from test_cloudflare import access, outside, token  # noqa: F401

from app import auth, keys, models
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


def test_manage_cookie_flags(client, configure):
    configure(COOKIE_DOMAIN="local.example.ch")
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


# Second checks behind the first ones (tests review 2026-11-07): each refuses on its own, should the first one change


def signed(claims: dict) -> str:
    key, kid = keys.signing_key()
    full = {"iss": auth.ISSUER, "exp": datetime.now(timezone.utc) + timedelta(minutes=5), **claims}
    return jwt.encode(full, key, algorithm=auth.ALGORITHM, headers={"kid": kid})


def test_manage_cookie_must_name_the_same_person(client, db):
    lena = make_person(db, "Lena", role="PARENT")
    admin = models.Person.by_name(db, "Admin")
    jti = uuid.uuid4().hex
    session = signed({"typ": "session", "sub": str(admin.id), "ver": admin.token_version, "jti": jti})
    # Lena's manage token, made for the Admin's very login
    manage = signed({"typ": "manage", "sub": str(lena.id), "ver": lena.token_version, "sid": jti})
    client.cookies.set(auth.COOKIE, session)
    client.cookies.set(auth.MANAGE_COOKIE, manage)
    assert client.get("/api/me").status_code == 200
    refused = client.patch("/api/me", json={"color": "#123456"})
    assert refused.status_code == 403 and refused.json()["detail"] == "login_again"


def test_one_kind_of_token_never_counts_as_the_other(db):
    session, manage = auth.issue_tokens(models.Person.by_name(db, "Admin"))
    assert auth.token_claims(session, "session") and auth.token_claims(manage, "manage")
    assert auth.token_claims(manage, "session") is None
    assert auth.token_claims(session, "manage") is None
    # A manage token given as the login cookie is no login, even with a made-up id of a login
    admin = models.Person.by_name(db, "Admin")
    with_jti = signed({"typ": "manage", "sub": str(admin.id), "ver": admin.token_version, "jti": "x", "sid": "x"})
    assert auth.person_for_token(db, with_jti) is None
