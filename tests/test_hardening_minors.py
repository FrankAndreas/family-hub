"""The deferred minors of the security review of the hub hardening (2026-10-30), each pinned by a test.
Invented people and addresses."""

import threading
import time

from fastapi.testclient import TestClient
from helpers import APP_HEADER
from test_pin_reset import ask, confirm, mail, with_email  # noqa: F401

from app import auth, pin_reset
from app.main import app


def device():
    return TestClient(app, headers=APP_HEADER)


def at_once(count, work):
    threads = [threading.Thread(target=work) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


# 4. A reset link works once even when it is used twice at the same moment; the hourly limit holds the same way
def test_a_link_works_once_even_at_the_same_moment(client, db, mail, monkeypatch):  # noqa: F811
    with_email(db)
    ask(client)
    token = mail.token()
    real = auth.new_pin

    def slow(person, pin):
        time.sleep(0.2)
        real(person, pin)

    monkeypatch.setattr(auth, "new_pin", slow)
    codes: list[int] = []
    at_once(2, lambda: codes.append(confirm(device(), token).status_code))
    assert sorted(codes) == [200, 400]


def test_three_per_hour_at_the_same_moment(client, db, mail, monkeypatch):  # noqa: F811
    with_email(db)
    real = pin_reset.create_link

    def slow(db_, person):
        time.sleep(0.1)
        return real(db_, person)

    monkeypatch.setattr(pin_reset, "create_link", slow)
    at_once(6, lambda: device().post("/api/pin-reset", json={"name": "Admin"}))
    pin_reset.flush()
    assert len(mail.mails) == pin_reset.MAX_PER_HOUR


# 5. The answer doesn't wait for the mail: how long it takes would tell who has an address
def test_answer_doesnt_wait_for_the_mail(client, db, mail, monkeypatch):  # noqa: F811
    with_email(db)
    release = threading.Event()

    def slow(*args):
        release.wait(5)
        mail(*args)

    monkeypatch.setattr(pin_reset, "resend_send", slow)
    start = time.monotonic()
    response = client.post("/api/pin-reset", json={"name": "Admin"})
    took = time.monotonic() - start
    release.set()
    pin_reset.flush()
    assert response.status_code == 200 and took < 1
    assert len(mail.mails) == 1
