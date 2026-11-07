"""Mails from the hub through the Resend API: a link for a forgotten PIN or a new e-mail address.

Mails go out after the answer (security review 2026-10-30): how long the answer took would tell who has an address, and
Resend's round trip shouldn't hold a request. One at a time is plenty for a family. No link, token or address reaches a
log line."""

import html
import json
import logging
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor

from . import config

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
TIMEOUT_SECONDS = 20

_mailer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mailer")
_pending: list[Future] = []


def is_configured() -> bool:
    return config.settings().mail_configured


def resend_send(mail_from: str, to: list[str], subject: str, text: str, html_body: str) -> None:
    outbox = config.settings().mail_outbox
    if outbox:
        # Only the browser tests set it: they read the mails from this file instead of sending them
        with open(outbox, "a", encoding="utf-8") as file:
            file.write(json.dumps({"to": to, "subject": subject, "text": text}) + "\n")
        return
    request = urllib.request.Request(
        RESEND_URL,
        data=json.dumps({"from": mail_from, "to": to, "subject": subject, "text": text, "html": html_body}).encode(),
        headers={
            "Authorization": f"Bearer {config.settings().resend_api_key}",
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


def _bodies(text: str, link: str) -> tuple[str, str]:
    """The plain text, and the same as simple HTML with the link clickable (everything escaped)."""
    safe = html.escape(text).replace(html.escape(link), f'<a href="{html.escape(link)}">{html.escape(link)}</a>')
    return text, "<p>" + safe.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"


def send_link(to: str, subject: str, text: str, link: str, kind: str) -> None:
    """Mail `text` (which contains `link`) to one address, in the background. `kind` names it in a failure's log
    line."""
    text, html_body = _bodies(text, link)
    mail_from = config.settings().mail_from
    # Looked up now, not at import: tests replace it
    send = resend_send

    def deliver() -> None:
        try:
            send(mail_from, [to], subject, text, html_body)
        except Exception as error:  # noqa: BLE001 - whatever went wrong, nobody waits for it
            logger.warning("%s mail failed: %s", kind, type(error).__name__)

    _pending.append(_mailer.submit(deliver))
