"""A forgotten PIN (spec 2026-10-30 hub hardening, part 3): a link by e-mail through the Resend API, or printed on the
NAS (app.reset_pin). The token sits after "#", which browsers never send, so no access log holds it. Only the
link's SHA-256 is kept; it works once, for 30 minutes, and at home only (links.py).

Nothing tells a stranger whether a name or an address exists."""

from datetime import timedelta

from sqlalchemy.orm import Session

from . import auth, links, mailer, models
from .errors import api_error

LINK_LIFETIME = timedelta(minutes=30)
MAX_PER_HOUR = 3
KIND = links.Kind(models.PinReset, "reset-pin", LINK_LIFETIME, MAX_PER_HOUR)

TEXTS = {
    "de": {
        "subject": "Familien-Hub: neue PIN",
        "body": (
            "Hallo {name}\n\n"
            "Mit diesem Link setzt du eine neue PIN für den Familien-Hub:\n\n{link}\n\n"
            "Er funktioniert nur zu Hause und 30 Minuten lang. Hast du keine neue PIN verlangt, kannst du diese "
            "E-Mail einfach löschen."
        ),
    },
    "en": {
        "subject": "Family hub: new PIN",
        "body": (
            "Hello {name}\n\n"
            "Use this link to set a new PIN for the family hub:\n\n{link}\n\n"
            "It only works at home, for 30 minutes. If you didn't ask for a new PIN, just delete this e-mail."
        ),
    },
}


def create_link(db: Session, person: models.Person) -> str:
    """A new reset link for the person: the full address, or only the path when HUB_PUBLIC_URL is unset."""
    return links.create(db, KIND, person)


def request_reset(db: Session, name: str) -> None:
    """Mail a reset link to the person with this name, if they are active, have an address and haven't had
    MAX_PER_HOUR links in the last hour. Never raises and never tells which case it was."""
    if not mailer.is_configured():
        return
    person = models.Person.by_name(db, name)
    if person is None or not person.active or not person.email:
        return
    link = links.create_limited(db, KIND, person)
    if link is None:
        return
    texts = TEXTS[person.language_or_default]
    text = texts["body"].format(name=person.name, link=link)
    mailer.send_link(person.email, texts["subject"], text, link, "PIN reset")


def end_links(db: Session, person: models.Person) -> None:
    """The person's open reset links stop working (a new e-mail address, deactivated); the caller commits."""
    links.end_open(db, KIND, person)


def confirm(db: Session, token: str, pin: str) -> None:
    """Set the new PIN with a reset link: it ends the person's logins, lifts a lock and every other open link."""
    invalid = api_error(400, "reset_link_invalid")
    reset = links.claim(db, KIND, token)
    if reset is None:
        raise invalid
    person = db.get(models.Person, reset.person_id)
    if person is None or not person.active:
        raise invalid
    auth.new_pin(person, pin)
    end_links(db, person)
    db.commit()
