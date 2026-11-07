"""Outside, Cloudflare Access is the login: its signed token names the person by e-mail. A test key plays Cloudflare
(helpers, the `access` fixture). A comment above a test names the review it came from, if any."""

import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from helpers import CF_KEY, CF_TEAM, THROUGH_TUNNEL, budget_tile, make_person, outside, token

from app import cloudflare, models


def test_token_names_the_person(client, db, access):
    make_person(db, "Mama", role="PARENT", email="Mama@Example.ch")
    me = client.get("/api/me", headers=outside(token("MAMA@example.ch")))
    assert me.status_code == 200 and me.json()["name"] == "Mama"
    # The second app's audience counts too; the certs were fetched once
    assert client.get("/api/me", headers=outside(token(aud="aud-of-the-apps"))).status_code == 200
    assert access == [f"https://{CF_TEAM}/cdn-cgi/access/certs"]


def test_refused(client, db, access):
    make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    make_person(db, "Tim", email="tim@example.ch", active=False)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for bad in (
        token("nobody@example.ch"),
        token("tim@example.ch"),
        token(aud="someone-else"),
        token(minutes=-5),
        token(issuer="https://evil.cloudflareaccess.com"),
        token(key=other),
        # Cloudflare always sets them; a token without one would never expire or fit any application
        token(leave_out=("exp",)),
        token(leave_out=("aud",)),
        token(leave_out=("iss",)),
        "nonsense",
    ):
        assert client.get("/api/me", headers=outside(bad)).status_code == 401, bad
    assert client.get("/api/me", headers=THROUGH_TUNNEL).status_code == 401


def test_not_configured(client, db, configure):
    make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    configure(CF_TEAM_DOMAIN=None)
    assert client.get("/api/me", headers=outside(token())).status_code == 401


def test_certs_fetched_again_after_an_hour(client, db, access, monkeypatch):
    make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    client.get("/api/me", headers=outside(token()))
    later = cloudflare.time.monotonic() + cloudflare.CERTS_FOR + 1
    monkeypatch.setattr(cloudflare.time, "monotonic", lambda: later)
    client.get("/api/me", headers=outside(token()))
    assert len(access) == 2


# Security review 2026-10-29
def test_broken_cloudflare_keys_fail_closed_without_errors(client, db, access, monkeypatch):
    make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    for broken in ({"keys": [{"kty": "RSA"}]}, ValueError("not json")):

        def fetch(url, broken=broken):
            if isinstance(broken, Exception):
                raise broken
            return broken

        monkeypatch.setattr(cloudflare, "_fetch", fetch)
        cloudflare._certs.clear()
        assert client.get("/api/me", headers=outside(token())).status_code == 401


# Security review 2026-10-29
def test_unknown_key_id_fetches_the_keys_again_once(client, db, access, monkeypatch):
    make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    # Keys fetched some minutes ago, before Cloudflare rotated: the new kid isn't among them
    cloudflare._certs[cloudflare.config.settings().cf_team_domain] = (time.monotonic() - 300, {})
    assert client.get("/api/me", headers=outside(token())).status_code == 200
    assert len(access) == 1
    # A made-up kid right after doesn't make the hub ask Cloudflare again (one try per minute at most)
    made_up = jwt.encode(
        jwt.decode(token(), options={"verify_signature": False}), CF_KEY, algorithm="RS256", headers={"kid": "nope"}
    )
    assert client.get("/api/me", headers=outside(made_up)).status_code == 401
    assert len(access) == 1


def test_a_cloudflare_token_counts_for_nothing_at_home(client, db, access):
    """Security review 2026-11-07: without Cf-Connecting-Ip the request didn't come through Cloudflare, so its token
    may have leaked (an app's log); at home only the hub's own login counts."""
    make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    budget_tile(db, models.Person.by_name(db, "Mama"))
    at_home = {"Cf-Access-Jwt-Assertion": token()}
    assert client.get("/api/session", headers=at_home).json()["valid"] is False
    assert client.get("/api/session?app=budget", headers=at_home).json()["valid"] is False
    assert client.get("/api/apps/budget/people", headers=at_home).status_code == 401
    assert client.get("/api/me", headers=at_home).status_code == 401
