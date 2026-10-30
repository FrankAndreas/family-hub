"""Apps check a hub login with the public key (JWKS) and ask /api/session whether it still counts."""

from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from helpers import login, make_person

from app import auth, keys, models


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_key_made_once_and_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _, kid = keys.signing_key()
    assert (tmp_path / keys.FILE).stat().st_mode & 0o777 == 0o600
    # A restart reads the same key
    keys._loaded.clear()
    assert keys.signing_key()[1] == kid


def test_jwks_verifies_a_hub_token(client):
    token = login(client).cookies.get("hub_session") or client.cookies.get("hub_session")
    found = client.get("/api/keys").json()
    assert client.get("/.well-known/jwks.json").json() == found
    [jwk] = found["keys"]
    assert (jwk["kty"], jwk["crv"], jwk["alg"]) == ("OKP", "Ed25519", "EdDSA")
    assert jwt.get_unverified_header(token)["kid"] == jwk["kid"]
    claims = jwt.decode(token, jwt.PyJWK(jwk).key, algorithms=["EdDSA"], issuer="family-hub")
    assert claims["sub"] == "1"


def test_session_for_apps(client, db):
    lena = make_person(db, "Lena", email="lena@example.ch", color="#f59e0b")
    token = auth.issue_token(lena)
    found = client.get("/api/session", headers=bearer(token)).json()
    assert found == {
        "valid": True,
        "person": {
            "id": lena.id,
            "name": "Lena",
            "email": "lena@example.ch",
            "role": "CHILD",
            "color": "#f59e0b",
            "language": "de",
        },
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
    token = auth.issue_token(lena)
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
    tile = models.Tile(name="Budget", local_url="https://budget.local.example.ch", app_key="budget")
    db.add(tile)
    db.commit()
    headers = bearer(auth.issue_token(lena))
    # The login is valid either way; access says whether this app is hers
    found = client.get("/api/session", params={"app": "budget"}, headers=headers).json()
    assert (found["valid"], found["access"]) == (True, False)
    tile.people.append(lena)
    db.commit()
    assert client.get("/api/session", params={"app": "budget"}, headers=headers).json()["access"] is True
    assert client.get("/api/session", params={"app": "nope"}, headers=headers).json()["access"] is False
    assert "access" not in client.get("/api/session", headers=headers).json()
