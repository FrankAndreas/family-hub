"""A forgotten PIN (spec 2026-10-30 hub hardening, part 3): a link by e-mail through the Resend API, or printed on the
NAS (app.reset_pin). The token sits after "#", which browsers never send, so no access log holds it. Only the
link's SHA-256 is kept; it works once, for 30 minutes, and at home only.

Nothing tells a stranger whether a name or an address exists, and no link, token or address reaches a log line."""

import hashlib
import html
import json
import logging
import secrets
import threading
import urllib.request
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import timedelta

from sqlalchemy.orm import Session

from . import auth, config, models
from .errors import api_error
from .timeutil import utcnow

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
LINK_LIFETIME = timedelta(minutes=30)
MAX_PER_HOUR = 3
TIMEOUT_SECONDS = 20

# (mail_from, to, subject, text, html)
Sender = Callable[[str, list[str], str, str, str], None]

# Mails go out after the answer (security review 2026-10-30): how long the answer took would tell who has an address,
# and Resend's round trip shouldn't hold a request. One at a time is plenty for a family
_mailer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mailer")
_pending: list[Future] = []
# Counting the links of the last hour and adding one happen together, so requests at once can't pass the limit
_limit_lock = threading.Lock()

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


def is_configured() -> bool:
    return all(config.env(name) for name in ("RESEND_API_KEY", "MAIL_FROM", "HUB_PUBLIC_URL"))


def resend_send(mail_from: str, to: list[str], subject: str, text: str, html_body: str) -> None:
    outbox = config.env("MAIL_OUTBOX")
    if outbox:
        # Only the browser tests set it: they read the mails from this file instead of sending them
        with open(outbox, "a", encoding="utf-8") as file:
            file.write(json.dumps({"to": to, "subject": subject, "text": text}) + "\n")
        return
    request = urllib.request.Request(
        RESEND_URL,
        data=json.dumps({"from": mail_from, "to": to, "subject": subject, "text": text, "html": html_body}).encode(),
        headers={
            "Authorization": f"Bearer {config.env('RESEND_API_KEY')}",
            "Content-Type": "application/json",
            "User-Agent": "family-hub",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):  # nosec B310 - Resend's fixed https URL
        pass


def flush() -> None:
    """Wait for the mails handed to the mailer so far (tests; mails are otherwise sent in the background)."""
    while _pending:
        _pending.pop(0).result()


def _send_later(send: Sender, mail_from: str, to: list[str], subject: str, text: str, html_body: str) -> None:
    def deliver() -> None:
        try:
            send(mail_from, to, subject, text, html_body)
        except Exception as error:  # noqa: BLE001 - whatever went wrong, nobody waits for it
            logger.warning("PIN reset mail failed: %s", type(error).__name__)

    _pending.append(_mailer.submit(deliver))


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_link(db: Session, person: models.Person) -> str:
    """A new reset link for the person: the full address, or only the path when HUB_PUBLIC_URL is unset."""
    token = secrets.token_urlsafe(32)
    now = utcnow()
    db.add(
        models.PinReset(person_id=person.id, token_hash=_hash(token), created_at=now, expires_at=now + LINK_LIFETIME)
    )
    db.commit()
    return f"{config.env('HUB_PUBLIC_URL').rstrip('/')}/reset-pin#token={token}"


def request_reset(db: Session, name: str, send: Sender | None = None) -> None:
    """Mail a reset link to the person with this name, if they are active, have an address and haven't had
    MAX_PER_HOUR links in the last hour. Never raises and never tells which case it was."""
    if not is_configured():
        return
    person = db.query(models.Person).filter(models.Person.name_key == auth.name_key(name)).first()
    if person is None or not person.active or not person.email:
        return
    with _limit_lock:
        recent = (
            db.query(models.PinReset)
            .filter(models.PinReset.person_id == person.id, models.PinReset.created_at > utcnow() - timedelta(hours=1))
            .count()
        )
        if recent >= MAX_PER_HOUR:
            return
        link = create_link(db, person)
    texts = TEXTS[person.language or config.default_language()]
    text = texts["body"].format(name=person.name, link=link)
    safe = html.escape(text).replace(html.escape(link), f'<a href="{html.escape(link)}">{html.escape(link)}</a>')
    html_body = "<p>" + safe.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
    # resend_send looked up now, not at import: tests replace it
    _send_later(send or resend_send, config.env("MAIL_FROM"), [person.email], texts["subject"], text, html_body)


def end_links(db: Session, person: models.Person) -> None:
    """The person's open reset links stop working (a new e-mail address, deactivated); the caller commits."""
    db.query(models.PinReset).filter(models.PinReset.person_id == person.id, models.PinReset.used_at.is_(None)).update(
        {models.PinReset.used_at: utcnow()}
    )


def confirm(db: Session, token: str, pin: str) -> None:
    """Set the new PIN with a reset link: it ends the person's logins, lifts a lock and every other open link."""
    invalid = api_error(400, "reset_link_invalid")
    now = utcnow()
    # Claimed in one step: of two uses at the same moment, only one finds the link unused (security review 2026-10-30)
    claimed = (
        db.query(models.PinReset)
        .filter(
            models.PinReset.token_hash == _hash(token),
            models.PinReset.used_at.is_(None),
            models.PinReset.expires_at >= now,
        )
        .update({models.PinReset.used_at: now})
    )
    db.commit()
    if claimed != 1:
        raise invalid
    reset = db.query(models.PinReset).filter(models.PinReset.token_hash == _hash(token)).one()
    person = db.get(models.Person, reset.person_id)
    if person is None or not person.active:
        raise invalid
    auth.new_pin(person, pin)
    end_links(db, person)
    db.commit()
