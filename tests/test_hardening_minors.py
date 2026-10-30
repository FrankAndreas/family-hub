"""The deferred minors of the security review of the hub hardening (2026-10-30), each pinned by a test.
Invented people and addresses."""

import re
import threading
import time
from datetime import timedelta

from fastapi.testclient import TestClient
from helpers import APP_HEADER, THROUGH_TUNNEL, add_person, login, make_person
from test_pin_reset import ask, confirm, mail, with_email  # noqa: F401

from app import auth, confirm_email, models, pin_reset
from app.main import app
from app.timeutil import utcnow


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


# 9. An address counts only once a link mailed to it was opened: a parent can't hand someone else's address (their
# Cloudflare login, their reset channel) to a child or a new person
def person_named(client, name):
    return next(p for p in client.get("/api/people").json() if p["name"] == name)


def confirm_link_token(outbox) -> str:
    found = re.search(r"/confirm-email#token=([A-Za-z0-9_-]+)", outbox.mails[-1]["text"])
    assert found, outbox.mails[-1]["text"]
    return found.group(1)


def test_new_address_counts_after_confirmation(client, db, mail):  # noqa: F811
    login(client)
    added = add_person(client, "Lena", email="lena@example.org")
    assert (added["email"], added["email_pending"]) == (None, "lena@example.org")
    pin_reset.flush()
    assert mail.mails[-1]["to"] == ["lena@example.org"]
    token = confirm_link_token(mail)
    # Not yet a way back in
    ask(client, "Lena")
    assert len(mail.mails) == 1
    assert client.post("/api/email-confirm", json={"token": token}).status_code == 200
    lena = person_named(client, "Lena")
    assert (lena["email"], lena["email_pending"]) == ("lena@example.org", None)
    again = client.post("/api/email-confirm", json={"token": token})
    assert again.status_code == 400 and again.json()["detail"] == "email_link_invalid"


def test_confirm_link_expires(client, db, mail):  # noqa: F811
    login(client)
    add_person(client, "Lena", email="lena@example.org")
    pin_reset.flush()
    db.query(models.EmailConfirm).update({models.EmailConfirm.expires_at: utcnow() - timedelta(minutes=1)})
    db.commit()
    assert client.post("/api/email-confirm", json={"token": confirm_link_token(mail)}).status_code == 400


def test_clearing_an_address_is_immediate(client, db, mail):  # noqa: F811
    login(client)
    lena = make_person(db, "Lena", email="lena@example.org")
    assert client.patch(f"/api/people/{lena.id}", json={"email": None}).json()["email"] is None


def test_address_taken_meanwhile(client, db, mail):  # noqa: F811
    login(client)
    add_person(client, "Lena", email="same@example.org")
    pin_reset.flush()
    lena_token = confirm_link_token(mail)
    add_person(client, "Max", email="same@example.org")
    pin_reset.flush()
    assert client.post("/api/email-confirm", json={"token": confirm_link_token(mail)}).status_code == 200
    taken = client.post("/api/email-confirm", json={"token": lena_token})
    assert taken.status_code == 409 and taken.json()["detail"] == "email_taken"


def test_confirm_not_through_the_tunnel(client, db, mail):  # noqa: F811
    login(client)
    add_person(client, "Lena", email="lena@example.org")
    pin_reset.flush()
    refused = client.post("/api/email-confirm", json={"token": confirm_link_token(mail)}, headers=THROUGH_TUNNEL)
    assert refused.status_code == 403


def test_nas_command_prints_a_confirm_link(client, db, monkeypatch, capsys):
    monkeypatch.setenv("HUB_PUBLIC_URL", "https://home.local.example.ch")
    login(client)
    add_person(client, "Lena", email="lena@example.org")
    assert confirm_email.main(["Lena"]) == 0
    found = re.search(r"/confirm-email#token=([A-Za-z0-9_-]+)", capsys.readouterr().out)
    assert found
    assert client.post("/api/email-confirm", json={"token": found.group(1)}).status_code == 200
    assert confirm_email.main(["Max"]) == 1


def test_saving_again_with_the_waiting_address_changes_nothing(client, db, mail):  # noqa: F811
    login(client)
    me = client.get("/api/me").json()["id"]
    client.patch(f"/api/people/{me}", json={"email": "admin@example.org", "current_pin": "1234"})
    pin_reset.flush()
    sent = len(mail.mails)
    # The form sends the address it shows: the waiting one; no PIN needed, and no new mail
    again = client.patch(f"/api/people/{me}", json={"email": "admin@example.org", "color": "#123456"})
    pin_reset.flush()
    assert again.status_code == 200 and again.json()["email_pending"] == "admin@example.org"
    assert len(mail.mails) == sent
