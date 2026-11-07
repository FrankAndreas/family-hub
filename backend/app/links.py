"""One-time links for a person: a forgotten PIN (pin_reset) or a new e-mail address (addresses), mailed or printed on
the NAS. Only the token's SHA-256 is kept, and the token sits after "#", which browsers never send, so no access log
holds it. A link works once, until it expires; at most a few are made per person and hour."""

import hashlib
import secrets
import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import cast

from sqlalchemy.orm import Session

from . import config, models
from .timeutil import utcnow

Link = models.PinReset | models.EmailConfirm


@dataclass(frozen=True)
class Kind:
    model: type[models.PinReset] | type[models.EmailConfirm]
    # The hub's page the link opens, e.g. "reset-pin"
    page: str
    lifetime: timedelta
    max_per_hour: int


# Counting the links of the last hour and adding one happen together, so requests at once can't pass the limit
_limit_lock = threading.Lock()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create(db: Session, kind: Kind, person: models.Person, **fields: str) -> str:
    """A new link: the full address, or only the path when HUB_PUBLIC_URL is unset. `fields`: the kind's own columns.
    The caller commits."""
    token = secrets.token_urlsafe(32)
    now = utcnow()
    db.add(
        kind.model(
            person_id=person.id, token_hash=_hash(token), created_at=now, expires_at=now + kind.lifetime, **fields
        )
    )
    db.flush()
    return f"{config.settings().hub_public_url}/{kind.page}#token={token}"


def create_limited(db: Session, kind: Kind, person: models.Person, **fields: str) -> str | None:
    """A new link, unless the person had `max_per_hour` of this kind in the last hour (None). Commits on purpose,
    under the lock: the next request counts this link."""
    with _limit_lock:
        recent = (
            db.query(kind.model)
            .filter(kind.model.person_id == person.id, kind.model.created_at > utcnow() - timedelta(hours=1))
            .count()
        )
        if recent >= kind.max_per_hour:
            return None
        link = create(db, kind, person, **fields)
        db.commit()
        return link


def claim(db: Session, kind: Kind, token: str) -> Link | None:
    """The link this token opens, now used; None if unknown, used or expired. Claimed in one step: of two uses at the
    same moment, only one finds the link unused (security review 2026-10-30). Commits on purpose: the link stays used
    even when what the caller does next fails."""
    now = utcnow()
    claimed = (
        db.query(kind.model)
        .filter(kind.model.token_hash == _hash(token), kind.model.used_at.is_(None), kind.model.expires_at >= now)
        .update({kind.model.used_at: now})
    )
    db.commit()
    if claimed != 1:
        return None
    return cast(Link, db.query(kind.model).filter(kind.model.token_hash == _hash(token)).one())


def has_open(db: Session, kind: Kind, person: models.Person) -> bool:
    """Whether the person has a link of this kind that still works (unused, not expired)."""
    return (
        db.query(kind.model)
        .filter(kind.model.person_id == person.id, kind.model.used_at.is_(None), kind.model.expires_at >= utcnow())
        .first()
        is not None
    )


def end_open(db: Session, kind: Kind, person: models.Person) -> None:
    """The person's open links of this kind stop working; the caller commits."""
    db.query(kind.model).filter(kind.model.person_id == person.id, kind.model.used_at.is_(None)).update(
        {kind.model.used_at: utcnow()}
    )
