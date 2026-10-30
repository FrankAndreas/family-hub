"""A person's e-mail address counts only once a link mailed to it was opened (security review 2026-10-30): the address
is the Cloudflare login and the way back in with a forgotten PIN, so a parent must not be able to hand someone else's
address to a child or a new person. Until then it waits in `email_pending`.

The link works once, for 24 hours, at home only; at most MAX_PER_HOUR mails per person. Without the mail settings, or
when the mail is lost, `python -m app.confirm_email <name>` prints the link on the NAS. As with PIN resets, no link,
token or address reaches a log line, and the token sits after "#".
"""

import hashlib
import secrets
import threading
from datetime import timedelta

from sqlalchemy.orm import Session

from . import config, models, pin_reset
from .errors import api_error
from .timeutil import utcnow

LINK_LIFETIME = timedelta(hours=24)
MAX_PER_HOUR = 3
_limit_lock = threading.Lock()

TEXTS = {
    "de": {
        "subject": "Familien-Hub: E-Mail-Adresse bestätigen",
        "body": (
            "Hallo {name}\n\n"
            "Im Familien-Hub wurde diese Adresse für dich eingetragen. Mit diesem Link bestätigst du sie:\n\n{link}\n\n"
            "Er funktioniert nur zu Hause und 24 Stunden lang. Kennst du den Familien-Hub nicht, lösche diese E-Mail "
            "einfach: ohne Bestätigung gilt die Adresse nicht."
        ),
    },
    "en": {
        "subject": "Family hub: confirm your e-mail address",
        "body": (
            "Hello {name}\n\n"
            "This address was entered for you in the family hub. Use this link to confirm it:\n\n{link}\n\n"
            "It only works at home, for 24 hours. If you don't know the family hub, just delete this e-mail: without "
            "confirmation the address doesn't count."
        ),
    },
}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _end_links(db: Session, person: models.Person) -> None:
    db.query(models.EmailConfirm).filter(
        models.EmailConfirm.person_id == person.id, models.EmailConfirm.used_at.is_(None)
    ).update({models.EmailConfirm.used_at: utcnow()})


def set_address(db: Session, person: models.Person, email: str | None) -> bool:
    """A parent set the person's address (cleaned, casefolded). Clearing it counts at once; a new one waits for its
    confirmation. Returns whether a confirmation mail is due (send_confirmation after the commit)."""
    if email is None or email == person.email:
        if email is None and person.email is not None:
            # Links mailed to the old address stop working
            pin_reset.end_links(db, person)
        person.email = email
        person.email_pending = None
        _end_links(db, person)
        return False
    person.email_pending = email
    _end_links(db, person)
    # The old address may be the reason for the change: its reset links stop working now
    pin_reset.end_links(db, person)
    return True


def create_link(db: Session, person: models.Person) -> str:
    """A confirmation link for the person's pending address: the full address, or the path without HUB_PUBLIC_URL."""
    assert person.email_pending is not None
    token = secrets.token_urlsafe(32)
    now = utcnow()
    db.add(
        models.EmailConfirm(
            person_id=person.id,
            email=person.email_pending,
            token_hash=_hash(token),
            created_at=now,
            expires_at=now + LINK_LIFETIME,
        )
    )
    db.commit()
    return f"{config.env('HUB_PUBLIC_URL').rstrip('/')}/confirm-email#token={token}"


def send_confirmation(db: Session, person: models.Person, send: pin_reset.Sender | None = None) -> None:
    """Mail a confirmation link to the person's pending address, if mails are set up and the hourly limit allows."""
    if not pin_reset.is_configured() or not person.email_pending:
        return
    with _limit_lock:
        recent = (
            db.query(models.EmailConfirm)
            .filter(
                models.EmailConfirm.person_id == person.id,
                models.EmailConfirm.created_at > utcnow() - timedelta(hours=1),
            )
            .count()
        )
        if recent >= MAX_PER_HOUR:
            return
        to = person.email_pending
        link = create_link(db, person)
    texts = TEXTS[person.language or config.default_language()]
    text, html_body = pin_reset.mail_bodies(texts["body"].format(name=person.name, link=link), link)
    pin_reset.send_later(
        send or pin_reset.resend_send, config.env("MAIL_FROM"), [to], texts["subject"], text, html_body, "Confirmation"
    )


def confirm(db: Session, token: str) -> None:
    """The address the link was mailed to becomes the person's address."""
    invalid = api_error(400, "email_link_invalid")
    now = utcnow()
    # Claimed in one step: of two uses at the same moment, only one finds the link unused
    claimed = (
        db.query(models.EmailConfirm)
        .filter(
            models.EmailConfirm.token_hash == _hash(token),
            models.EmailConfirm.used_at.is_(None),
            models.EmailConfirm.expires_at >= now,
        )
        .update({models.EmailConfirm.used_at: now})
    )
    db.commit()
    if claimed != 1:
        raise invalid
    link = db.query(models.EmailConfirm).filter(models.EmailConfirm.token_hash == _hash(token)).one()
    person = db.get(models.Person, link.person_id)
    if person is None or not person.active or person.email_pending != link.email:
        raise invalid
    other = db.query(models.Person).filter(models.Person.email == link.email, models.Person.id != person.id).first()
    if other is not None:
        raise api_error(409, "email_taken")
    person.email = link.email
    person.email_pending = None
    _end_links(db, person)
    pin_reset.end_links(db, person)
    db.commit()
