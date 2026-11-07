"""A forgotten PIN: a reset link by e-mail, or from the NAS as the last resort (spec 2026-10-30 hub hardening, part 3).
Invented people and addresses. A comment above a test names the review it came from, if any."""

import logging
import threading
import time
from datetime import timedelta

from fastapi.testclient import TestClient
from helpers import ADMIN, ADMIN_PIN, APP_HEADER, RESET_LINK, THROUGH_TUNNEL, device, login, make_person

from app import links, mailer, models, pin_reset, pins, reset_pin
from app.main import app
from app.timeutil import utcnow


def with_email(db, name=ADMIN, email="admin@example.org"):
    person = db.query(models.Person).filter(models.Person.name == name).one()
    person.email = email
    db.commit()
    return person


def ask(client, name=ADMIN):
    response = client.post("/api/pin-reset", json={"name": name})
    # The mail goes out after the answer
    mailer.flush()
    return response


def confirm(client, token, pin="2468"):
    return client.post("/api/pin-reset/confirm", json={"token": token, "pin": pin})


def at_once(count, work):
    threads = [threading.Thread(target=work) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def test_same_answer_for_everyone(client, db, mail, monkeypatch):
    with_email(db)
    make_person(db, "Lena")
    make_person(db, "Tim", email="tim@example.org", active=False)
    answers = [ask(client, name) for name in ("Admin", "Nobody", "Lena", "Tim")]
    assert {(a.status_code, a.text) for a in answers} == {(200, '{"ok":true}')}
    assert [m["to"] for m in mail.mails] == [["admin@example.org"]]
    mail.fail = True
    failed = ask(client)
    assert (failed.status_code, failed.text) == (200, '{"ok":true}')


def test_name_in_another_case(client, db, mail):
    with_email(db)
    ask(client, "  admin ")
    assert len(mail.mails) == 1


def test_three_per_hour(client, db, mail):
    with_email(db)
    for _ in range(4):
        ask(client)
    assert len(mail.mails) == pin_reset.MAX_PER_HOUR == 3


def test_link_works_once_and_ends_others(client, db, mail):
    with_email(db)
    login(client)
    ask(client)
    ask(client)
    first, second = mail.token(0), mail.token(1)
    assert confirm(client, second).status_code == 200
    again = confirm(client, second)
    assert again.status_code == 400 and again.json()["detail"] == "reset_link_invalid"
    assert confirm(client, first).status_code == 400
    # The new PIN ended the old login
    assert client.get("/api/me").status_code == 401
    login(client, ADMIN, "2468")


def test_link_expires(client, db, mail):
    with_email(db)
    ask(client)
    db.query(models.PinReset).update({models.PinReset.expires_at: utcnow() - timedelta(minutes=1)})
    db.commit()
    assert confirm(client, mail.token()).status_code == 400


def test_reset_lifts_the_lock(client, db, mail):
    with_email(db)
    for _ in range(5):
        client.post("/api/login", json={"name": ADMIN, "pin": "0000"})
    assert client.post("/api/login", json={"name": ADMIN, "pin": ADMIN_PIN}).status_code == 429
    ask(client)
    assert confirm(client, mail.token()).status_code == 200
    login(client, ADMIN, "2468")


def test_not_through_the_tunnel(client, db, mail):
    with_email(db)
    assert client.post("/api/pin-reset", json={"name": ADMIN}, headers=THROUGH_TUNNEL).status_code == 403
    ask(client)
    refused = client.post("/api/pin-reset/confirm", json={"token": mail.token(), "pin": "2468"}, headers=THROUGH_TUNNEL)
    assert refused.status_code == 403


def test_off_without_settings(client, db, monkeypatch, configure):
    configure(RESEND_API_KEY=None, MAIL_FROM=None, HUB_PUBLIC_URL=None)
    sent = []
    monkeypatch.setattr(mailer, "resend_send", lambda *args: sent.append(args))
    with_email(db)
    assert client.get("/api/config").json()["pin_reset"] is False
    assert ask(client).status_code == 200
    assert sent == []


def test_nothing_secret_in_logs(client, db, mail, caplog):
    caplog.set_level(logging.DEBUG)
    with_email(db)
    ask(client)
    token = mail.token()
    mail.fail = True
    ask(client)
    confirm(client, token)
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert token not in text and "reset-pin" not in text and "admin@example.org" not in text
    assert "PIN reset mail failed: OSError" in text


def test_mail_in_person_language(client, db, mail):
    with_email(db)
    lena = make_person(db, "Lena", email="lena@example.org")
    lena.language = "en"
    db.commit()
    ask(client, "Lena")
    ask(client, ADMIN)
    assert [m["subject"] for m in mail.mails] == ["Family hub: new PIN", "Familien-Hub: neue PIN"]


def test_nas_command_prints_a_working_link(client, db, configure, capsys):
    configure(HUB_PUBLIC_URL="https://home.local.example.ch")
    assert reset_pin.main([ADMIN]) == 0
    found = RESET_LINK.search(capsys.readouterr().out)
    assert found
    assert confirm(TestClient(app, headers=APP_HEADER), found.group(1)).status_code == 200
    assert reset_pin.main(["Nobody"]) == 1


# Security review 2026-10-30, finding 3: a new address is the answer to a mailbox someone else reads, so the links
# already sent there must stop working; so must a deactivated person's, even if they come back within the half hour
def test_links_end_with_a_new_address(client, db, mail):
    with_email(db)
    ask(client)
    token = mail.token()
    login(client)
    me = client.get("/api/me").json()["id"]
    changed = client.patch(f"/api/people/{me}", json={"email": "new@example.org", "current_pin": ADMIN_PIN})
    assert changed.status_code == 200
    assert confirm(client, token).status_code == 400


def test_links_end_when_deactivated(client, db, mail):
    lena = make_person(db, "Lena", email="lena@example.org")
    ask(client, "Lena")
    token = mail.token()
    login(client)
    assert client.patch(f"/api/people/{lena.id}", json={"active": False}).status_code == 200
    assert client.patch(f"/api/people/{lena.id}", json={"active": True}).status_code == 200
    assert confirm(client, token).status_code == 400


# Second check (tests review 2026-11-07): deactivating ends the links, but even an open one doesn't work for someone
# who is no longer active
def test_no_new_pin_for_someone_inactive(client, db, mail):
    lena = make_person(db, "Lena", email="lena@example.org")
    ask(client, "Lena")
    lena.active = False
    db.commit()
    refused = confirm(client, mail.token())
    assert refused.status_code == 400 and refused.json()["detail"] == "reset_link_invalid"


# Security review 2026-10-30, a deferred minor
# 4. A reset link works once even when it is used twice at the same moment; the hourly limit holds the same way
def test_a_link_works_once_even_at_the_same_moment(client, db, mail, monkeypatch):
    with_email(db)
    ask(client)
    token = mail.token()
    real = pins.new_pin

    def slow(person, pin):
        time.sleep(0.2)
        real(person, pin)

    monkeypatch.setattr(pins, "new_pin", slow)
    codes: list[int] = []
    at_once(2, lambda: codes.append(confirm(device(), token).status_code))
    assert sorted(codes) == [200, 400]


# Security review 2026-10-30, a deferred minor
def test_three_per_hour_at_the_same_moment(client, db, mail, monkeypatch):
    with_email(db)
    real = links.create

    def slow(db_, kind, person, **fields):
        time.sleep(0.1)
        return real(db_, kind, person, **fields)

    monkeypatch.setattr(links, "create", slow)
    at_once(6, lambda: device().post("/api/pin-reset", json={"name": "Admin"}))
    mailer.flush()
    assert len(mail.mails) == pin_reset.MAX_PER_HOUR


# Security review 2026-10-30, a deferred minor
# 5. The answer doesn't wait for the mail: how long it takes would tell who has an address
def test_answer_doesnt_wait_for_the_mail(client, db, mail, monkeypatch):
    with_email(db)
    release = threading.Event()

    def slow(*args):
        release.wait(5)
        mail(*args)

    monkeypatch.setattr(mailer, "resend_send", slow)
    start = time.monotonic()
    response = client.post("/api/pin-reset", json={"name": "Admin"})
    took = time.monotonic() - start
    release.set()
    mailer.flush()
    assert response.status_code == 200 and took < 1
    assert len(mail.mails) == 1
