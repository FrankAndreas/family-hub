"""The hub's tokens: signed with a key made once at start, published as JWKS; a session token and a manage token per
login, never standing in for each other. Invented people. A comment above a test names the review it came from, if
any."""

from datetime import datetime, timedelta, timezone

import jwt
from helpers import bearer_session, login, signed

from app import auth, config, keys, models


def test_key_made_once_and_kept(tmp_path, configure):
    configure(DATA_DIR=str(tmp_path))
    _, kid = keys.signing_key()
    assert (tmp_path / keys.FILE).stat().st_mode & 0o777 == 0o600
    # A restart reads the same key
    keys._loaded.clear()
    assert keys.signing_key()[1] == kid


# Security review 2026-10-29
def test_signing_key_made_at_start():
    # Made before the first request (no race between two first requests)
    assert (config.data_dir() / keys.FILE).exists()


def test_jwks_verifies_a_hub_token(client):
    token = login(client).cookies.get("hub_session") or client.cookies.get("hub_session")
    found = client.get("/api/keys").json()
    assert client.get("/.well-known/jwks.json").json() == found
    [jwk] = found["keys"]
    assert (jwk["kty"], jwk["crv"], jwk["alg"]) == ("OKP", "Ed25519", "EdDSA")
    assert jwt.get_unverified_header(token)["kid"] == jwk["kid"]
    claims = jwt.decode(token, jwt.PyJWK(jwk).key, algorithms=["EdDSA"], issuer="family-hub")
    assert claims["sub"] == "1"


# Hub hardening (spec 2026-10-30)
def test_manage_token_is_no_session(client):
    login(client)
    assert bearer_session(client.cookies.get(auth.MANAGE_COOKIE))["valid"] is False


# Hub hardening (spec 2026-10-30)
def test_old_token_without_jti_is_invalid(client, db):
    key, kid = keys.signing_key()
    person = db.query(models.Person).first()
    claims = {
        "iss": auth.ISSUER,
        "sub": str(person.id),
        "ver": person.token_version,
        "exp": datetime.now(timezone.utc) + timedelta(days=1),
    }
    client.cookies.set("hub_session", jwt.encode(claims, key, algorithm="EdDSA", headers={"kid": kid}))
    assert client.get("/api/me").status_code == 401


def test_one_kind_of_token_never_counts_as_the_other(db):
    session, manage = auth.issue_tokens(models.Person.by_name(db, "Admin"))
    assert auth.token_claims(session, "session") and auth.token_claims(manage, "manage")
    assert auth.token_claims(manage, "session") is None
    assert auth.token_claims(session, "manage") is None
    # A manage token given as the login cookie is no login, even with a made-up id of a login
    admin = models.Person.by_name(db, "Admin")
    with_jti = signed({"typ": "manage", "sub": str(admin.id), "ver": admin.token_version, "jti": "x", "sid": "x"})
    assert auth.person_for_token(db, with_jti) is None
