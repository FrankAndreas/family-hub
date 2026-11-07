"""What many tests share: logging in, people, other browsers, tokens, the Cloudflare test key, a mail outbox.
Invented people only: the repository is public."""

import re
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

ADMIN = "Admin"
ADMIN_PIN = "1234"
# Cloudflare sets this on every request that comes through the tunnel; the DSM reverse proxy at home doesn't
THROUGH_TUNNEL = {"Cf-Connecting-Ip": "203.0.113.7"}
# The hub's own pages send it with every change; another site can't make a browser send it
APP_HEADER = {"X-Requested-With": "hub"}

# A test key plays Cloudflare Access (the `access` fixture serves it as Cloudflare's keys)
CF_TEAM = "family.cloudflareaccess.com"
CF_AUD = "aud-of-the-hub"
CF_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

# The token after "#": browsers never send that part, so no access log on the way holds it (security review 2026-10-30)
RESET_LINK = re.compile(r"https://home\.local\.example\.ch/reset-pin#token=([A-Za-z0-9_-]+)")


def device() -> TestClient:
    """Another browser: its own cookies, nothing shared with the others."""
    from app.main import app

    return TestClient(app, headers=APP_HEADER)


def login(client, name=ADMIN, pin=ADMIN_PIN):
    """Log in at home: the client keeps the login cookie."""
    response = client.post("/api/login", json={"name": name, "pin": pin})
    assert response.status_code == 200, response.text
    return response


def own_id(client) -> int:
    return client.get("/api/me").json()["id"]


def add_person(client, name, pin="5678", role="CHILD", email=None, **fields) -> dict:
    body = {"name": name, "pin": pin, "role": role, "email": email, **fields}
    response = client.post("/api/people", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def make_person(db, name, pin="5678", role="CHILD", email=None, active=True, color=None):
    """A person straight in the database (before the people API exists in a test)."""
    from app import models, pins

    person = models.Person(
        name=name,
        name_key=models.name_key(name),
        email=email.casefold() if email else None,
        pin_hash=pins.get_pin_hash(pin),
        role=models.Role(role),
        active=active,
        color=color,
    )
    db.add(person)
    db.commit()
    return person


def budget_tile(db, *people):
    """The Budget app (key "budget") straight in the database, for these people."""
    from app import models

    tile = models.Tile(name="Budget", local_url="https://budget.local.example.ch", app_key="budget")
    tile.people.extend(people)
    db.add(tile)
    db.commit()
    return tile


def all_set_cookies(response) -> list[str]:
    return [v for k, v in response.headers.multi_items() if k == "set-cookie"]


def set_cookie(response, name) -> str:
    """The Set-Cookie header for this cookie."""
    return next(v for v in all_set_cookies(response) if v.startswith(f"{name}="))


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def bearer_session(token):
    """What /api/session tells an app that passes this token on."""
    from app.main import app

    return TestClient(app).get("/api/session", headers=bearer(token)).json()


def signed(claims: dict) -> str:
    """A hub token with these claims, signed with the hub's key (issuer and a few minutes' expiry added)."""
    from app import auth, keys

    key, kid = keys.signing_key()
    full = {"iss": auth.ISSUER, "exp": datetime.now(timezone.utc) + timedelta(minutes=5), **claims}
    return jwt.encode(full, key, algorithm=auth.ALGORITHM, headers={"kid": kid})


def token(email="mama@example.ch", aud=CF_AUD, minutes=60, issuer=f"https://{CF_TEAM}", key=CF_KEY, leave_out=()):
    """A Cloudflare Access token, as Cloudflare would sign it."""
    claims = {
        "email": email,
        "aud": [aud],
        "iss": issuer,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes),
    }
    claims = {k: v for k, v in claims.items() if k not in leave_out}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-kid"})


def outside(value):
    """The headers of a request through the tunnel with this Cloudflare token."""
    return {**THROUGH_TUNNEL, "Cf-Access-Jwt-Assertion": value}


class Outbox:
    """Takes the mails instead of Resend (the `mail` fixture)."""

    def __init__(self, fail=False):
        self.mails: list[dict] = []
        self.fail = fail

    def __call__(self, mail_from, to, subject, text, html):
        if self.fail:
            raise OSError("mail server down")
        self.mails.append({"from": mail_from, "to": to, "subject": subject, "text": text, "html": html})

    def token(self, index=-1) -> str:
        """The reset link's token in this mail."""
        found = RESET_LINK.search(self.mails[index]["text"])
        assert found, self.mails[index]["text"]
        return found.group(1)
