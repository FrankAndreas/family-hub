"""Findings of the security review (2026-10-29), each pinned by a test."""

import threading
import time

from fastapi.testclient import TestClient
from helpers import ADMIN_PIN, APP_HEADER, THROUGH_TUNNEL, login
from test_cloudflare import access, outside, token  # noqa: F401

from app import auth, cloudflare, config, keys
from app.main import app
from app.seed import seed_admin  # noqa: F401


def test_parallel_wrong_pins_count_every_try(monkeypatch):
    # Many guesses at once: each one counts, so no more than the allowed few get an answer before the lock
    real = auth.verify_pin

    def slow(pin, hashed):
        time.sleep(0.05)
        return real(pin, hashed)

    monkeypatch.setattr(auth, "verify_pin", slow)
    codes: list[int] = []

    def guess(n):
        response = TestClient(app, headers=APP_HEADER).post("/api/login", json={"name": "Admin", "pin": f"{n:04d}"})
        codes.append(response.status_code)

    threads = [threading.Thread(target=guess, args=(n,)) for n in range(2000, 2020)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert codes.count(401) <= auth.MAX_FAILED_LOGINS
    assert codes.count(429) == len(codes) - codes.count(401)


def test_own_pin_change_counts_wrong_old_pins(client):
    login(client)
    for _ in range(auth.MAX_FAILED_LOGINS):
        assert client.put("/api/me/pin", json={"old_pin": "0000", "pin": "1357"}).status_code == 401
    locked = client.put("/api/me/pin", json={"old_pin": ADMIN_PIN, "pin": "1357"})
    assert locked.status_code == 429


def test_session_through_the_tunnel_ignores_a_hub_token(client, db):
    hub_token = login(client).cookies.get("hub_session") or client.cookies.get("hub_session")
    headers = {"Authorization": f"Bearer {hub_token}"}
    assert client.get("/api/session", headers=headers).json()["valid"] is True
    # The same token from an outside request (the app passes Cf-Connecting-Ip on): only Cloudflare's counts
    assert client.get("/api/session", headers={**headers, **THROUGH_TUNNEL}).json()["valid"] is False


def test_broken_cloudflare_keys_fail_closed_without_errors(client, db, access, monkeypatch):  # noqa: F811
    from helpers import make_person

    make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    for broken in ({"keys": [{"kty": "RSA"}]}, ValueError("not json")):

        def fetch(url, broken=broken):
            if isinstance(broken, Exception):
                raise broken
            return broken

        monkeypatch.setattr(cloudflare, "_fetch", fetch)
        cloudflare._certs.clear()
        assert client.get("/api/me", headers=outside(token())).status_code == 401


def test_unknown_key_id_fetches_the_keys_again_once(client, db, access, monkeypatch):  # noqa: F811
    from helpers import make_person

    make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    # Keys fetched some minutes ago, before Cloudflare rotated: the new kid isn't among them
    cloudflare._certs[cloudflare.config.env("CF_TEAM_DOMAIN")] = (time.monotonic() - 300, {})
    assert client.get("/api/me", headers=outside(token())).status_code == 200
    assert len(access) == 1
    # A made-up kid right after doesn't make the hub ask Cloudflare again (one try per minute at most)
    import jwt
    from test_cloudflare import KEY

    made_up = jwt.encode(
        jwt.decode(token(), options={"verify_signature": False}), KEY, algorithm="RS256", headers={"kid": "nope"}
    )
    assert client.get("/api/me", headers=outside(made_up)).status_code == 401
    assert len(access) == 1


def test_signing_key_made_at_start():
    # Made before the first request (no race between two first requests)
    assert (config.data_dir() / keys.FILE).exists()


def test_managing_only_at_home(client, db, access):  # noqa: F811
    # A parent logged in through Cloudflare (a mailbox someone broke into) can't take over the family's accounts
    from helpers import make_person

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
