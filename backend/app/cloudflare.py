"""Outside, Cloudflare Access is the login (spec 2026-10-29). Every request through the tunnel carries Cloudflare's
signed token (Cf-Access-Jwt-Assertion) with the person's e-mail address; it is checked against the team's public keys
and the Access applications' audiences (CF_AUDIENCE, comma-separated), then matched to an active person by e-mail.
Without CF_TEAM_DOMAIN and CF_AUDIENCE, nobody is logged in from outside."""

import json
import logging
import time
import urllib.request

import jwt
from fastapi import Request
from sqlalchemy.orm import Session

from . import config, models

logger = logging.getLogger(__name__)

HEADER = "cf-access-jwt-assertion"
# Cloudflare rotates its keys every few weeks and keeps the old one valid meanwhile; an hour is plenty
CERTS_FOR = 3600
TIMEOUT_SECONDS = 10
_certs: dict[str, tuple[float, dict]] = {}


def _fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
        found = json.load(response)
    return found if isinstance(found, dict) else {}


def _keys(team: str) -> dict:
    """The team's public keys by kid, fetched at most once an hour."""
    now = time.monotonic()
    cached = _certs.get(team)
    if cached is None or now - cached[0] > CERTS_FOR:
        url = f"https://{team}/cdn-cgi/access/certs"
        _certs[team] = (now, {k["kid"]: k for k in _fetch(url).get("keys", [])})
        cached = _certs[team]
    return cached[1]


def person_for_token(db: Session, token: str | None) -> models.Person | None:
    team = config.env("CF_TEAM_DOMAIN")
    audiences = [a.strip() for a in config.env("CF_AUDIENCE").split(",") if a.strip()]
    if not token or not team or not audiences:
        return None
    try:
        kid = jwt.get_unverified_header(token).get("kid")
        jwk = _keys(team).get(kid)
        if jwk is None:
            return None
        claims = jwt.decode(
            token, jwt.PyJWK(jwk).key, algorithms=["RS256"], audience=audiences, issuer=f"https://{team}"
        )
    except jwt.PyJWTError:
        return None
    except OSError as error:
        logger.warning("Cloudflare Access keys not reachable: %s", type(error).__name__)
        return None
    email = str(claims.get("email") or "").strip().casefold()
    if not email:
        return None
    return db.query(models.Person).filter(models.Person.email == email, models.Person.active.is_(True)).first()


def person_for(request: Request, db: Session) -> models.Person | None:
    return person_for_token(db, request.headers.get(HEADER))
