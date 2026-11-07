"""Managing people, PINs and apps: at home only, and with the manage cookie only the hub gets (spec 2026-10-30 hub
hardening, part 1). Invented people. A comment above a test names the review it came from, if any."""

import uuid

from helpers import ADMIN_PIN, THROUGH_TUNNEL, device, login, make_person, outside, set_cookie, signed, token

from app import auth, models


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
    header = set_cookie(login(client), "hub_manage")
    assert "Domain=" not in header
    assert "HttpOnly" in header and "SameSite=strict" in header and "Path=/api" in header


def test_own_pin_change_keeps_managing(client):
    login(client)
    assert client.put("/api/me/pin", json={"old_pin": ADMIN_PIN, "pin": "1357"}).status_code == 200
    assert client.get("/api/people").status_code == 200


# Second check behind the first ones (tests review 2026-11-07): refuses on its own, should the first one change
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


# Security review 2026-10-29
def test_managing_only_at_home(client, db, access):
    # A parent logged in through Cloudflare (a mailbox someone broke into) can't take over the family's accounts
    mama = make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    headers = outside(token())
    me = client.get("/api/me", headers=headers).json()
    assert (me["name"], me["at_home"]) == ("Mama", False)
    refused = [
        client.get("/api/people", headers=headers),
        client.post("/api/people", json={"name": "Tim", "pin": "1111", "role": "CHILD"}, headers=headers),
        client.patch(f"/api/people/{mama.id}", json={"email": "evil@example.com"}, headers=headers),
        client.put(f"/api/people/{mama.id}/pin", json={"pin": "1111"}, headers=headers),
        client.put("/api/me/pin", json={"old_pin": "5678", "pin": "1111"}, headers=headers),
        client.get("/api/tiles/manage", headers=headers),
        client.post("/api/tiles", json={"name": "X", "local_url": "https://x.example.ch"}, headers=headers),
        client.put("/api/tiles/order", json=[], headers=headers),
    ]
    for response in refused:
        assert response.status_code == 403 and response.json()["detail"] == "manage_at_home_only", response.url
    # Using the apps and one's own settings still works outside
    assert client.get("/api/tiles", headers=headers).status_code == 200
    assert client.patch("/api/me", json={"language": "en"}, headers=headers).status_code == 200
    # At home the same parent manages everything
    login(client, "Mama", "5678")
    assert client.get("/api/me").json()["at_home"] is True
    assert client.get("/api/people").status_code == 200


def test_outside_can_still_change_own_colour(client, db, access):
    make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    response = client.patch("/api/me", json={"color": "#112233"}, headers=outside(token()))
    assert response.status_code == 200


def test_managing_people_from_outside_needs_cloudflare(client):
    login(client)
    assert client.get("/api/people", headers=THROUGH_TUNNEL).status_code == 401
