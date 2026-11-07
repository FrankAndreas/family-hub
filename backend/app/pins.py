"""PINs: checking them, locking a person after too many wrong ones, and the browsers a person logged in with before
(spec 2026-10-29, security review 2026-10-30)."""

import hashlib
import math
import secrets
import threading
from datetime import timedelta

import bcrypt
from fastapi import Response, status
from sqlalchemy.orm import Session

from . import config, models
from .errors import api_error
from .timeutil import utcnow

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


def get_pin_hash(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def verify_pin(pin: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pin.encode(), hashed.encode())
    except ValueError:
        # Not a valid bcrypt hash: treat it like a wrong PIN instead of a server error
        return False


def lock_duration(lockouts: int) -> timedelta:
    """15, 30, 60, ... minutes for the first, second, third lock in a row; at most a day."""
    duration: timedelta = LOCK_DURATION * 2 ** min(max(lockouts - 1, 0), 10)
    return min(duration, MAX_LOCK_DURATION)


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
    alone: after MAX_FAILED_LOGINS of them it is unknown again.

    Commits on purpose, while the person's lock is held: a wrong PIN counts although the request fails, and a parallel
    guess reads the count only after it is written."""
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
    person = models.Person.by_name(db, name)
    if person is None or not person.active:
        raise wrong
    check_pin(db, person, pin, wrong, device_secret)
    return person


def remember_device(db: Session, response: Response, person: models.Person, secret: str | None) -> None:
    """After a correct login: this browser is known for the person from now on (the caller commits). Its cookie stays
    with the hub (no domain), so the other apps at home never get it."""
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
    assert secret is not None
    response.set_cookie(
        DEVICE_COOKIE,
        secret,
        max_age=int(DEVICE_LIFETIME.total_seconds()),
        path="/api",
        secure=config.settings().cookie_secure,
        httponly=True,
        samesite="strict",
    )
