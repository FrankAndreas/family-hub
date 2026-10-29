"""The PIN login at home: a cookie every app at home gets; never through the Cloudflare tunnel. Invented people."""

from datetime import timedelta

from helpers import ADMIN_PIN, THROUGH_TUNNEL, login, make_person

from app import models


def cookie_header(response) -> str:
    return next(v for k, v in response.headers.multi_items() if k == "set-cookie" and v.startswith("hub_session="))


def test_login_sets_the_cookie(client, monkeypatch):
    monkeypatch.setenv("COOKIE_DOMAIN", "local.example.ch")
    response = login(client)
    header = cookie_header(response)
    assert "HttpOnly" in header and "SameSite=lax" in header and "Domain=local.example.ch" in header
    assert f"Max-Age={int(timedelta(days=30).total_seconds())}" in header
    # Tests talk plain http (COOKIE_INSECURE=1); on the NAS the cookie is Secure
    assert "Secure" not in header
    monkeypatch.delenv("COOKIE_INSECURE")
    assert "Secure" in cookie_header(login(client))


def test_me_after_login(client):
    assert client.get("/api/me").status_code == 401
    login(client)
    me = client.get("/api/me").json()
    assert (me["name"], me["role"], me["language"]) == ("Admin", "PARENT", "de")


def test_wrong_pin_and_lockout(client):
    for _ in range(4):
        assert client.post("/api/login", json={"name": "admin", "pin": "0000"}).status_code == 401
    assert client.post("/api/login", json={"name": "Admin", "pin": "0000"}).status_code == 401
    # Locked now, even with the right PIN
    response = client.post("/api/login", json={"name": "Admin", "pin": ADMIN_PIN})
    assert response.status_code == 429 and response.json()["detail"]["code"] == "locked"


def test_inactive_person_cant_log_in(client, db):
    make_person(db, "Lena", active=False)
    assert client.post("/api/login", json={"name": "Lena", "pin": "5678"}).status_code == 401


def test_logout_clears_the_cookie(client):
    login(client)
    response = client.post("/api/logout")
    assert response.status_code == 200 and 'hub_session=""' in cookie_header(response)
    assert client.get("/api/me").status_code == 401


def test_logout_everywhere_ends_older_logins(client):
    login(client)
    old = client.cookies.get("hub_session")
    assert client.post("/api/logout-everywhere").status_code == 200
    client.cookies.set("hub_session", old)
    assert client.get("/api/me").status_code == 401


def test_deactivated_ends_logins(client, db):
    make_person(db, "Lena")
    login(client, "Lena", "5678")
    person = db.query(models.Person).filter(models.Person.name == "Lena").one()
    person.active = False
    db.commit()
    assert client.get("/api/me").status_code == 401


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
