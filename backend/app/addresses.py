"""A person's e-mail address counts only once a link mailed to it was opened (security review 2026-10-30): the address
is the Cloudflare login and the way back in with a forgotten PIN, so a parent must not be able to hand someone else's
address to a child or a new person. Until then it waits in `email_pending`.

The link works once, for 24 hours, at home only; at most MAX_PER_HOUR mails per person. Without the mail settings, or
when the mail is lost, `python -m app.confirm_email <name>` prints the link on the NAS. As with PIN resets, no link,
token or address reaches a log line, and the token sits after "#".
"""

from datetime import timedelta

from sqlalchemy.orm import Session

from . import links, mailer, models, pin_reset
from .errors import api_error

LINK_LIFETIME = timedelta(hours=24)
MAX_PER_HOUR = 3
KIND = links.Kind(models.EmailConfirm, "confirm-email", LINK_LIFETIME, MAX_PER_HOUR)

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


def set_address(db: Session, person: models.Person, email: str | None) -> bool:
    """A parent set the person's address (cleaned, casefolded). Clearing it counts at once; a new one waits for its
    confirmation. Returns whether a confirmation mail is due (send_confirmation after the commit)."""
    if email is None or email == person.email:
        if email is None and person.email is not None:
            # Links mailed to the old address stop working
            pin_reset.end_links(db, person)
        person.email = email
        person.email_pending = None
        links.end_open(db, KIND, person)
        return False
    person.email_pending = email
    links.end_open(db, KIND, person)
    # The old address may be the reason for the change: its reset links stop working now
    pin_reset.end_links(db, person)
    return True


def create_link(db: Session, person: models.Person) -> str:
    """A confirmation link for the person's pending address: the full address, or the path without HUB_PUBLIC_URL.
    The caller commits."""
    assert person.email_pending is not None
    return links.create(db, KIND, person, email=person.email_pending)


def send_confirmation(db: Session, person: models.Person) -> None:
    """Mail a confirmation link to the person's pending address, if mails are set up and the hourly limit allows."""
    to = person.email_pending
    if not mailer.is_configured() or not to:
        return
    link = links.create_limited(db, KIND, person, email=to)
    if link is None:
        return
    texts = TEXTS[person.language_or_default]
    text = texts["body"].format(name=person.name, link=link)
    mailer.send_link(to, texts["subject"], text, link, "Confirmation")


def link_lost(db: Session, person: models.Person) -> bool:
    """The person's address waits, but no link to it works any more (expired or used): saving it again sends a new
    one, as the "link expired" message says."""
    return person.email_pending is not None and not links.has_open(db, KIND, person)


def confirm(db: Session, token: str) -> None:
    """The address the link was mailed to becomes the person's address. The caller commits."""
    invalid = api_error(400, "email_link_invalid")
    link = links.claim(db, KIND, token)
    if not isinstance(link, models.EmailConfirm):
        raise invalid
    person = db.get(models.Person, link.person_id)
    if person is None or not person.active or person.email_pending != link.email:
        raise invalid
    other = db.query(models.Person).filter(models.Person.email == link.email, models.Person.id != person.id).first()
    if other is not None:
        raise api_error(409, "email_taken")
    person.email = link.email
    person.email_pending = None
    links.end_open(db, KIND, person)
    pin_reset.end_links(db, person)
