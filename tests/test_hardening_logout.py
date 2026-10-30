"""Logging out ends this login for real; session and manage tokens (spec 2026-10-30 hub hardening). Invented people."""

from datetime import datetime, timedelta, timezone

import jwt
from alembic import command
from fastapi.testclient import TestClient
from helpers import APP_HEADER, login
from sqlalchemy import create_engine

from app import auth, database_setup, keys, models
from app.main import app
from app.timeutil import utcnow


def device():
    return TestClient(app, headers=APP_HEADER)


def bearer_session(token):
    return TestClient(app).get("/api/session", headers={"Authorization": f"Bearer {token}"}).json()


def set_cookies(response) -> list[str]:
    return [v for k, v in response.headers.multi_items() if k == "set-cookie"]


def test_logout_ends_this_login_only(client):
    login(client)
    other = device()
    login(other)
    token = client.cookies.get("hub_session")
    assert client.post("/api/logout").status_code == 200
    assert bearer_session(token)["valid"] is False
    assert other.get("/api/me").status_code == 200


def test_logout_clears_both_cookies(client):
    login(client)
    cookies = set_cookies(client.post("/api/logout"))
    assert any(c.startswith('hub_session=""') for c in cookies)
    assert any(c.startswith('hub_manage=""') for c in cookies)


def test_ended_logins_are_cleaned_up(client, db):
    db.add(models.EndedLogin(jti="0" * 32, expires_at=utcnow() - timedelta(days=1)))
    db.commit()
    login(client)
    client.post("/api/logout")
    db.expire_all()
    assert db.get(models.EndedLogin, "0" * 32) is None


def test_manage_token_is_no_session(client):
    login(client)
    assert bearer_session(client.cookies.get(auth.MANAGE_COOKIE))["valid"] is False


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


def test_migration_logs_everyone_out(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/m.db")
    database_setup.run(engine, command.upgrade, "0003")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO people (name, name_key, pin_hash, role, active, failed_logins, lockouts, token_version,"
            " created_at) VALUES ('Mia', 'mia', 'x', 'PARENT', 1, 0, 0, 0, '2026-10-30 10:00:00')"
        )
    database_setup.setup(engine)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT token_version FROM people").scalar() == 1
