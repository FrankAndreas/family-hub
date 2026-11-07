"""Apps ask /api/session whether a login still counts, and whether the app is the person's. A comment above a test
names the review it came from, if any."""

from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from helpers import THROUGH_TUNNEL, bearer, budget_tile, login, make_person, outside, token

from app import auth, keys, models


def test_session_for_apps(client, db):
    lena = make_person(db, "Lena", email="lena@example.ch", color="#f59e0b")
    token = auth.issue_tokens(lena)[0]
    found = client.get("/api/session", headers=bearer(token)).json()
    assert found == {
        "valid": True,
        "person": {"id": lena.id, "name": "Lena", "role": "CHILD", "color": "#f59e0b", "language": "de"},
        "renew": False,
    }
    # The cookie at home counts as well
    login(client, "Lena", "5678")
    assert client.get("/api/session").json()["valid"] is True


def test_session_invalid(client, db):
    lena = make_person(db, "Lena")
    other = Ed25519PrivateKey.generate()
    claims = {"iss": "family-hub", "sub": str(lena.id), "ver": 0}
    foreign = jwt.encode({**claims, "exp": datetime.now(timezone.utc) + timedelta(days=1)}, other, algorithm="EdDSA")
    key, _ = keys.signing_key()
    expired = jwt.encode({**claims, "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, key, algorithm="EdDSA")
    token = auth.issue_tokens(lena)[0]
    for bad in (foreign, expired, "nonsense"):
        assert client.get("/api/session", headers=bearer(bad)).json() == {"valid": False, "person": None}
    # Logged out everywhere, or no longer active: earlier tokens end
    person = db.get(models.Person, lena.id)
    person.token_version += 1
    db.commit()
    assert client.get("/api/session", headers=bearer(token)).json()["valid"] is False
    person.token_version -= 1
    person.active = False
    db.commit()
    assert client.get("/api/session", headers=bearer(token)).json()["valid"] is False
    assert client.get("/api/session").json() == {"valid": False, "person": None}


def test_session_access_per_app(client, db):
    lena = make_person(db, "Lena")
    tile = budget_tile(db)
    headers = bearer(auth.issue_tokens(lena)[0])
    # The login is valid either way; access says whether this app is hers
    found = client.get("/api/session", params={"app": "budget"}, headers=headers).json()
    assert (found["valid"], found["access"]) == (True, False)
    tile.people.append(lena)
    db.commit()
    assert client.get("/api/session", params={"app": "budget"}, headers=headers).json()["access"] is True
    assert client.get("/api/session", params={"app": "nope"}, headers=headers).json()["access"] is False
    assert "access" not in client.get("/api/session", headers=headers).json()


# Security review 2026-10-29
def test_session_through_the_tunnel_ignores_a_hub_token(client, db):
    hub_token = login(client).cookies.get("hub_session") or client.cookies.get("hub_session")
    headers = {"Authorization": f"Bearer {hub_token}"}
    assert client.get("/api/session", headers=headers).json()["valid"] is True
    # The same token from an outside request (the app passes Cf-Connecting-Ip on): only Cloudflare's counts
    assert client.get("/api/session", headers={**headers, **THROUGH_TUNNEL}).json()["valid"] is False


def test_apps_pass_the_cloudflare_token_to_the_session(client, db, access):
    make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    found = client.get("/api/session", headers=outside(token(aud="aud-of-the-apps"))).json()
    assert found["valid"] is True and found["person"]["name"] == "Mama"
    assert client.get("/api/session", headers=outside(token("x@example.ch"))).json()["valid"] is False


# App integration review 2026-11-07: the person's address only for an app whose tile allows it, as in the app's people.
# Else every app would learn each address as its owner logs in
def test_the_address_only_for_an_app_allowed_to_see_it(client, db):
    lena = make_person(db, "Lena", email="lena@example.ch")
    tile = budget_tile(db, lena)
    headers = bearer(auth.issue_tokens(lena)[0])

    def person(**params):
        return client.get("/api/session", params=params, headers=headers).json()["person"]

    assert "email" not in person(app="budget") and "email" not in person()
    tile.share_email = True
    db.commit()
    assert person(app="budget")["email"] == "lena@example.ch"
    assert "email" not in person() and "email" not in person(app="nope")


# App integration review 2026-11-07: someone who only opens apps never opens the hub, which renews a login (auth.renew).
# In its last week the session says so, and the app sends the browser through the hub once
def test_a_login_in_its_last_week_asks_to_be_renewed(client, db, monkeypatch):
    lena = make_person(db, "Lena")
    fresh = auth.issue_tokens(lena)[0]
    monkeypatch.setattr(auth, "TOKEN_LIFETIME", timedelta(days=7) - timedelta(minutes=1))
    old = auth.issue_tokens(lena)[0]
    assert client.get("/api/session", headers=bearer(fresh)).json()["renew"] is False
    assert client.get("/api/session", headers=bearer(old)).json()["renew"] is True
    # No longer valid: nothing to renew
    db.get(models.Person, lena.id).token_version += 1
    db.commit()
    assert "renew" not in client.get("/api/session", headers=bearer(old)).json()


def test_cloudflare_logins_are_not_renewed_by_the_hub(client, db, access):
    make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    assert client.get("/api/session", headers=outside(token())).json()["renew"] is False
