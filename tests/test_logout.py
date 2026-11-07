"""Logging out ends this login for real, in the hub and every app; logging out everywhere ends them all. Invented
people. A comment above a test names the review it came from, if any."""

from datetime import timedelta

from helpers import all_set_cookies, bearer_session, device, login, make_person, set_cookie

from app import models
from app.timeutil import utcnow


def test_logout_clears_the_cookie(client):
    login(client)
    response = client.post("/api/logout")
    assert response.status_code == 200 and 'hub_session=""' in set_cookie(response, "hub_session")
    assert client.get("/api/me").status_code == 401


# Hub hardening (spec 2026-10-30)
def test_logout_clears_both_cookies(client):
    login(client)
    cookies = all_set_cookies(client.post("/api/logout"))
    assert any(c.startswith('hub_session=""') for c in cookies)
    assert any(c.startswith('hub_manage=""') for c in cookies)


# Hub hardening (spec 2026-10-30)
def test_logout_ends_this_login_only(client):
    login(client)
    other = device()
    login(other)
    token = client.cookies.get("hub_session")
    assert client.post("/api/logout").status_code == 200
    assert bearer_session(token)["valid"] is False
    assert other.get("/api/me").status_code == 200


# Hub hardening (spec 2026-10-30)
def test_ended_logins_are_cleaned_up(client, db):
    db.add(models.EndedLogin(jti="0" * 32, expires_at=utcnow() - timedelta(days=1)))
    db.commit()
    login(client)
    client.post("/api/logout")
    db.expire_all()
    assert db.get(models.EndedLogin, "0" * 32) is None


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
