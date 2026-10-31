"""Outside, Cloudflare Access is the login: its signed token names the person by e-mail. A test key plays Cloudflare."""

import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from helpers import THROUGH_TUNNEL, make_person

from app import cloudflare

TEAM = "family.cloudflareaccess.com"
AUD = "aud-of-the-hub"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def access(monkeypatch):
    monkeypatch.setenv("CF_TEAM_DOMAIN", TEAM)
    monkeypatch.setenv("CF_AUDIENCE", f"{AUD}, aud-of-the-apps")
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key()))
    fetched = []

    def fetch(url):
        fetched.append(url)
        return {"keys": [{**jwk, "kid": "test-kid", "alg": "RS256"}]}

    monkeypatch.setattr(cloudflare, "_fetch", fetch)
    cloudflare._certs.clear()
    return fetched


def token(email="mama@example.ch", aud=AUD, minutes=60, issuer=f"https://{TEAM}", key=KEY, leave_out=()):
    claims = {
        "email": email,
        "aud": [aud],
        "iss": issuer,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes),
    }
    claims = {k: v for k, v in claims.items() if k not in leave_out}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-kid"})


def outside(value):
    return {**THROUGH_TUNNEL, "Cf-Access-Jwt-Assertion": value}


def test_token_names_the_person(client, db, access):
    make_person(db, "Mama", role="PARENT", email="Mama@Example.ch")
    me = client.get("/api/me", headers=outside(token("MAMA@example.ch")))
    assert me.status_code == 200 and me.json()["name"] == "Mama"
    # The second app's audience counts too; the certs were fetched once
    assert client.get("/api/me", headers=outside(token(aud="aud-of-the-apps"))).status_code == 200
    assert access == [f"https://{TEAM}/cdn-cgi/access/certs"]


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


def test_not_configured(client, db, monkeypatch):
    make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    monkeypatch.delenv("CF_TEAM_DOMAIN", raising=False)
    assert client.get("/api/me", headers=outside(token())).status_code == 401


def test_certs_fetched_again_after_an_hour(client, db, access, monkeypatch):
    make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    client.get("/api/me", headers=outside(token()))
    later = cloudflare.time.monotonic() + cloudflare.CERTS_FOR + 1
    monkeypatch.setattr(cloudflare.time, "monotonic", lambda: later)
    client.get("/api/me", headers=outside(token()))
    assert len(access) == 2


def test_apps_pass_the_cloudflare_token_to_the_session(client, db, access):
    make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    found = client.get("/api/session", headers={"Cf-Access-Jwt-Assertion": token(aud="aud-of-the-apps")}).json()
    assert found["valid"] is True and found["person"]["name"] == "Mama"
    assert (
        client.get("/api/session", headers={"Cf-Access-Jwt-Assertion": token("x@example.ch")}).json()["valid"] is False
    )
