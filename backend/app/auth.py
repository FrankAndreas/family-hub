"""The family login: a PIN at home, Cloudflare Access outside (spec 2026-10-29).

At home the PIN login sets the cookie `hub_session` for COOKIE_DOMAIN (e.g. local.<domain>), so every app at home gets
it and the addresses through Cloudflare never do. A request that came through the Cloudflare tunnel (it carries
Cf-Connecting-Ip) gets no PIN login and its cookie counts for nothing: outside, only a Cloudflare Access token does.
"""

import hashlib
import logging
import math
import secrets
import threading
import uuid
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
# Only the hub gets it: managing people, PINs and apps needs it as well (spec 2026-10-30 hub hardening)
MANAGE_COOKIE = "hub_manage"
ISSUER = "family-hub"
ALGORITHM = "EdDSA"
TOKEN_LIFETIME = timedelta(days=30)
# A 4-digit PIN is guessable, so lock the person after a few wrong tries. Each lock in a row doubles the next one, up
# to a day: then about 5 guesses a day are left
MAX_FAILED_LOGINS = 5
LOCK_DURATION = timedelta(minutes=15)
MAX_LOCK_DURATION = timedelta(days=1)
# A browser the person logged in with before (security review 2026-10-30): wrong PINs from other devices don't lock it
DEVICE_COOKIE = "hub_device"
DEVICE_LIFETIME = timedelta(days=365)
# Known browsers kept per person; the oldest is forgotten first
MAX_DEVICES = 20
# The hub's own pages send it with every change; another page on the family's domain can't make a browser send it
APP_HEADER = "x-requested-with"
APP_HEADER_VALUE = "hub"
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


def new_pin(person: models.Person, pin: str) -> None:
    """A new PIN ends every login made with the old one and lifts a lock."""
    person.pin_hash = get_pin_hash(pin)
    person.token_version += 1
    person.failed_logins = 0
    person.lockouts = 0
    person.locked_until = None


def _secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def known_device(db: Session, person: models.Person, secret: str | None) -> models.KnownDevice | None:
    if not secret:
        return None
    return (
        db.query(models.KnownDevice)
        .filter(models.KnownDevice.person_id == person.id, models.KnownDevice.secret_hash == _secret_hash(secret))
        .first()
    )


def check_pin(db: Session, person: models.Person, pin: str, wrong: Exception, device_secret: str | None = None) -> None:
    """The person's PIN, counting wrong ones and locking the person after too many; raises `wrong` or 429.

    From a browser the person logged in with before, the lock doesn't apply and wrong PINs count against that browser
    alone: after MAX_FAILED_LOGINS of them it is unknown again."""
    with _pin_lock(person.id):
        # What other requests counted meanwhile
        db.refresh(person)
        device = known_device(db, person, device_secret)
        now = utcnow()
        if device is None and person.locked_until and person.locked_until > now:
            minutes = math.ceil((person.locked_until - now).total_seconds() / 60)
            raise api_error(status.HTTP_429_TOO_MANY_REQUESTS, "locked", minutes=minutes)
        if not verify_pin(pin, person.pin_hash):
            if device is not None:
                device.failed_logins += 1
                if device.failed_logins >= MAX_FAILED_LOGINS:
                    db.delete(device)
            else:
                person.failed_logins += 1
                if person.failed_logins >= MAX_FAILED_LOGINS:
                    person.failed_logins = 0
                    person.lockouts += 1
                    person.locked_until = now + lock_duration(person.lockouts)
            db.commit()
            raise wrong
        if device is not None:
            device.failed_logins = 0
        person.failed_logins = 0
        person.lockouts = 0
        person.locked_until = None
        db.commit()


def authenticate(db: Session, name: str, pin: str, device_secret: str | None = None) -> models.Person:
    """The active person with this name and PIN; counts wrong PINs and locks the person after too many."""
    wrong = api_error(status.HTTP_401_UNAUTHORIZED, "wrong_name_or_pin")
    person = db.query(models.Person).filter(models.Person.name_key == name_key(name)).first()
    if person is None or not person.active:
        raise wrong
    check_pin(db, person, pin, wrong, device_secret)
    return person


def remember_device(db: Session, response: Response, person: models.Person, secret: str | None) -> None:
    """After a correct login: this browser is known for the person from now on. Its cookie stays with the hub (no
    domain), so the other apps at home never get it."""
    if known_device(db, person, secret) is None:
        secret = secret or secrets.token_urlsafe(32)
        db.add(models.KnownDevice(person_id=person.id, secret_hash=_secret_hash(secret)))
        db.flush()
        kept = (
            db.query(models.KnownDevice.id)
            .filter(models.KnownDevice.person_id == person.id)
            .order_by(models.KnownDevice.id.desc())
            .limit(MAX_DEVICES)
        )
        db.query(models.KnownDevice).filter(
            models.KnownDevice.person_id == person.id, models.KnownDevice.id.not_in(kept.scalar_subquery())
        ).delete(synchronize_session=False)
        db.commit()
    assert secret is not None
    response.set_cookie(
        DEVICE_COOKIE,
        secret,
        max_age=int(DEVICE_LIFETIME.total_seconds()),
        path="/api",
        secure=config.env("COOKIE_INSECURE") != "1",
        httponly=True,
        samesite="strict",
    )


def require_app_header(request: Request) -> None:
    """Changes come from the hub's own pages only (security review 2026-10-30). The login cookie is SameSite=lax, so
    every page on the family's domain (any app at home) could otherwise make a browser send it with a change."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(APP_HEADER) != APP_HEADER_VALUE:
        raise api_error(status.HTTP_403_FORBIDDEN, "csrf")


def issue_tokens(person: models.Person) -> tuple[str, str]:
    """A login: the session token every app at home gets, and the manage token only the hub gets (spec 2026-10-30 hub
    hardening). The session's id (jti) lets "Log out" end exactly this login; the manage token names it (sid)."""
    key, kid = keys.signing_key()
    common = {
        "iss": ISSUER,
        "sub": str(person.id),
        "ver": person.token_version,
        "exp": datetime.now(timezone.utc) + TOKEN_LIFETIME,
    }
    jti = uuid.uuid4().hex
    session = jwt.encode({**common, "typ": "session", "jti": jti}, key, algorithm=ALGORITHM, headers={"kid": kid})
    manage = jwt.encode({**common, "typ": "manage", "sid": jti}, key, algorithm=ALGORITHM, headers={"kid": kid})
    return session, manage


def token_claims(token: str | None, typ: str) -> dict | None:
    """The claims of a hub token of this type, if it is ours and not expired; any other token is None."""
    if not token:
        return None
    key, _ = keys.signing_key()
    try:
        claims = jwt.decode(token, key.public_key(), algorithms=[ALGORITHM], issuer=ISSUER)
    except jwt.PyJWTError:
        return None
    return claims if claims.get("typ") == typ else None


def _ended(db: Session, jti: object) -> bool:
    return not isinstance(jti, str) or db.get(models.EndedLogin, jti) is not None


def _person(db: Session, claims: dict) -> models.Person | None:
    try:
        person_id, version = int(claims["sub"]), int(claims["ver"])
    except KeyError, ValueError, TypeError:
        return None
    person = db.get(models.Person, person_id)
    if person is None or not person.active or person.token_version != version:
        return None
    return person


def person_for_token(db: Session, token: str | None) -> models.Person | None:
    """The person a session token names, if it is ours, not expired, not logged out, not ended everywhere
    (token_version) and the person is active."""
    claims = token_claims(token, "session")
    if claims is None or _ended(db, claims.get("jti")):
        return None
    return _person(db, claims)


def end_login(db: Session, token: str | None) -> None:
    """ "Log out": this session token is no login any more, here or in any app. Ended logins that would have expired
    by now are dropped."""
    now = utcnow()
    db.query(models.EndedLogin).filter(models.EndedLogin.expires_at < now).delete()
    claims = token_claims(token, "session")
    jti = claims.get("jti") if claims else None
    if isinstance(jti, str) and db.get(models.EndedLogin, jti) is None:
        expires = datetime.fromtimestamp(int(claims["exp"]), timezone.utc).replace(tzinfo=None)  # type: ignore[index]
        db.add(models.EndedLogin(jti=jti, expires_at=expires))
    db.commit()


def _secure() -> bool:
    return config.env("COOKIE_INSECURE") != "1"


def set_cookies(response: Response, session: str, manage: str) -> None:
    """The session cookie for every app at home (COOKIE_DOMAIN); the manage cookie for the hub alone (no domain)."""
    max_age = int(TOKEN_LIFETIME.total_seconds())
    response.set_cookie(
        COOKIE,
        session,
        max_age=max_age,
        domain=config.env("COOKIE_DOMAIN") or None,
        secure=_secure(),
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        MANAGE_COOKIE, manage, max_age=max_age, path="/api", secure=_secure(), httponly=True, samesite="strict"
    )


def clear_cookies(response: Response) -> None:
    response.delete_cookie(
        COOKIE, domain=config.env("COOKIE_DOMAIN") or None, secure=_secure(), httponly=True, samesite="lax"
    )
    response.delete_cookie(MANAGE_COOKIE, path="/api", secure=_secure(), httponly=True, samesite="strict")


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


def require_manage_at_home(request: Request) -> None:
    """Managing people, PINs and apps happens at home only (the user's choice, 2026-10-29): a parent's mailbox someone
    broke into gets past Cloudflare Access, but must not take over the family's accounts."""
    if through_tunnel(request):
        raise api_error(status.HTTP_403_FORBIDDEN, "manage_at_home_only")


def require_manager(
    request: Request, person: models.Person = Depends(current_person), db: Session = Depends(database.get_db)
) -> models.Person:
    """Whoever changes something in the hub, at home, with the manage cookie of this very login (spec 2026-10-30 hub
    hardening): the session cookie alone, which every app at home gets, manages nothing."""
    require_manage_at_home(request)
    session = token_claims(request.cookies.get(COOKIE), "session")
    manage = token_claims(request.cookies.get(MANAGE_COOKIE), "manage")
    if session is None or manage is None or manage.get("sid") != session.get("jti"):
        raise api_error(status.HTTP_403_FORBIDDEN, "login_again")
    owner = _person(db, manage)
    if owner is None or owner.id != person.id:
        raise api_error(status.HTTP_403_FORBIDDEN, "login_again")
    return person


def require_parent(person: models.Person = Depends(require_manager)) -> models.Person:
    """A parent, at home, with the manage cookie: every parent right is about managing the family."""
    if person.role != models.Role.PARENT:
        raise api_error(status.HTTP_403_FORBIDDEN, "parents_only")
    return person


def require_home(request: Request) -> None:
    if through_tunnel(request):
        raise api_error(status.HTTP_403_FORBIDDEN, "login_at_home_only")
