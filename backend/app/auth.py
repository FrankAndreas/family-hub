"""The family login: a PIN at home, Cloudflare Access outside (spec 2026-10-29).

At home the PIN login sets the cookie `hub_session` for COOKIE_DOMAIN (e.g. local.<domain>), so every app at home gets
it and the addresses through Cloudflare never do. A request that came through the Cloudflare tunnel (it carries
Cf-Connecting-Ip) gets no PIN login and its cookie counts for nothing: outside, only a Cloudflare Access token does.
"""

import logging
import math
import threading
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Request, Response, status
from sqlalchemy.orm import Session

from . import cloudflare, config, database, keys, models
from .errors import api_error
from .timeutil import utcnow

logger = logging.getLogger(__name__)

COOKIE = "hub_session"
ISSUER = "family-hub"
ALGORITHM = "EdDSA"
TOKEN_LIFETIME = timedelta(days=30)
# A 4-digit PIN is guessable, so lock the person after a few wrong tries. Each lock in a row doubles the next one, up
# to a day: then about 5 guesses a day are left
MAX_FAILED_LOGINS = 5
LOCK_DURATION = timedelta(minutes=15)
MAX_LOCK_DURATION = timedelta(days=1)
# Cloudflare sets it on every request through the tunnel; the DSM reverse proxy at home doesn't
TUNNEL_HEADER = "cf-connecting-ip"


def get_pin_hash(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def verify_pin(pin: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pin.encode(), hashed.encode())
    except ValueError:
        # Not a valid bcrypt hash: treat it like a wrong PIN instead of a server error
        return False


def name_key(name: str) -> str:
    """What makes two names the same person's: case and surrounding spaces don't count."""
    return name.strip().casefold()


def lock_duration(lockouts: int) -> timedelta:
    """15, 30, 60, ... minutes for the first, second, third lock in a row; at most a day."""
    duration: timedelta = LOCK_DURATION * 2 ** min(max(lockouts - 1, 0), 10)
    return min(duration, MAX_LOCK_DURATION)


def through_tunnel(request: Request) -> bool:
    return TUNNEL_HEADER in request.headers


# One PIN check per person at a time (security review 2026-10-29): parallel guesses would each read the same count of
# wrong PINs while bcrypt runs, and get far more tries than MAX_FAILED_LOGINS. The backend is one process (uvicorn
# without workers), so a lock in memory is enough
_pin_locks: dict[int, threading.Lock] = {}
_pin_locks_guard = threading.Lock()


def _pin_lock(person_id: int) -> threading.Lock:
    with _pin_locks_guard:
        return _pin_locks.setdefault(person_id, threading.Lock())


def check_pin(db: Session, person: models.Person, pin: str, wrong: Exception) -> None:
    """The person's PIN, counting wrong ones and locking the person after too many; raises `wrong` or 429."""
    with _pin_lock(person.id):
        # What other requests counted meanwhile
        db.refresh(person)
        now = utcnow()
        if person.locked_until and person.locked_until > now:
            minutes = math.ceil((person.locked_until - now).total_seconds() / 60)
            raise api_error(status.HTTP_429_TOO_MANY_REQUESTS, "locked", minutes=minutes)
        if not verify_pin(pin, person.pin_hash):
            person.failed_logins += 1
            if person.failed_logins >= MAX_FAILED_LOGINS:
                person.failed_logins = 0
                person.lockouts += 1
                person.locked_until = now + lock_duration(person.lockouts)
            db.commit()
            raise wrong
        person.failed_logins = 0
        person.lockouts = 0
        person.locked_until = None
        db.commit()


def authenticate(db: Session, name: str, pin: str) -> models.Person:
    """The active person with this name and PIN; counts wrong PINs and locks the person after too many."""
    wrong = api_error(status.HTTP_401_UNAUTHORIZED, "wrong_name_or_pin")
    person = db.query(models.Person).filter(models.Person.name_key == name_key(name)).first()
    if person is None or not person.active:
        raise wrong
    check_pin(db, person, pin, wrong)
    return person


def issue_token(person: models.Person) -> str:
    key, kid = keys.signing_key()
    claims = {
        "iss": ISSUER,
        "sub": str(person.id),
        "ver": person.token_version,
        "exp": datetime.now(timezone.utc) + TOKEN_LIFETIME,
    }
    return jwt.encode(claims, key, algorithm=ALGORITHM, headers={"kid": kid})


def person_for_token(db: Session, token: str | None) -> models.Person | None:
    """The person a hub token names, if it is ours, not expired, not ended (token_version) and the person is active."""
    if not token:
        return None
    key, _ = keys.signing_key()
    try:
        claims = jwt.decode(token, key.public_key(), algorithms=[ALGORITHM], issuer=ISSUER)
        person_id, version = int(claims["sub"]), int(claims["ver"])
    except jwt.PyJWTError, KeyError, ValueError, TypeError:
        return None
    person = db.get(models.Person, person_id)
    if person is None or not person.active or person.token_version != version:
        return None
    return person


def set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=int(TOKEN_LIFETIME.total_seconds()),
        domain=config.env("COOKIE_DOMAIN") or None,
        secure=config.env("COOKIE_INSECURE") != "1",
        httponly=True,
        samesite="lax",
    )


def clear_cookie(response: Response) -> None:
    response.delete_cookie(
        COOKIE,
        domain=config.env("COOKIE_DOMAIN") or None,
        secure=config.env("COOKIE_INSECURE") != "1",
        httponly=True,
        samesite="lax",
    )


def current_person_or_none(request: Request, db: Session) -> models.Person | None:
    """Who is asking: outside the Cloudflare Access token, at home the hub cookie."""
    if through_tunnel(request):
        return cloudflare.person_for(request, db)
    return person_for_token(db, request.cookies.get(COOKIE))


def current_person(request: Request, db: Session = Depends(database.get_db)) -> models.Person:
    person = current_person_or_none(request, db)
    if person is None:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "not_logged_in")
    return person


def require_parent(person: models.Person = Depends(current_person)) -> models.Person:
    if person.role != models.Role.PARENT:
        raise api_error(status.HTTP_403_FORBIDDEN, "parents_only")
    return person


def require_home(request: Request) -> None:
    if through_tunnel(request):
        raise api_error(status.HTTP_403_FORBIDDEN, "login_at_home_only")
