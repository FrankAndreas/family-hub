"""The mail itself: what the hub sends to Resend (every other test replaces this request), and the browser tests'
outbox file. Invented addresses."""

import json

from app import mailer


class Sent:
    request = None
    timeout = None


def test_the_request_to_resend(monkeypatch, configure):
    configure(RESEND_API_KEY="re_test_key", MAIL_OUTBOX=None)
    sent = Sent()

    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout):
        sent.request, sent.timeout = request, timeout
        return Answer()

    monkeypatch.setattr(mailer.urllib.request, "urlopen", urlopen)
    mailer.resend_send("hub@example.org", ["lena@example.org"], "Subject", "Text", "<p>Text</p>")

    request = sent.request
    assert request is not None
    assert (request.full_url, request.get_method()) == ("https://api.resend.com/emails", "POST")
    assert request.get_header("Authorization") == "Bearer re_test_key"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data) == {
        "from": "hub@example.org",
        "to": ["lena@example.org"],
        "subject": "Subject",
        "text": "Text",
        "html": "<p>Text</p>",
    }
    # A Resend that hangs never holds the mailer for ever
    assert sent.timeout == mailer.TIMEOUT_SECONDS


def test_the_browser_tests_outbox(monkeypatch, configure, tmp_path):
    outbox = tmp_path / "outbox.jsonl"
    configure(RESEND_API_KEY="re_test_key", MAIL_OUTBOX=str(outbox))

    def urlopen(*args, **kwargs):
        raise AssertionError("no mail leaves the machine")

    monkeypatch.setattr(mailer.urllib.request, "urlopen", urlopen)
    mailer.resend_send("hub@example.org", ["lena@example.org"], "Subject", "Text", "<p>Text</p>")
    mailer.resend_send("hub@example.org", ["max@example.org"], "Other", "More", "<p>More</p>")
    lines = [json.loads(line) for line in outbox.read_text().splitlines()]
    assert lines == [
        {"to": ["lena@example.org"], "subject": "Subject", "text": "Text"},
        {"to": ["max@example.org"], "subject": "Other", "text": "More"},
    ]
