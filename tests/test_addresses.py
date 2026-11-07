"""An e-mail address counts only once a link mailed to it was opened: a parent can't hand someone else's address (their
Cloudflare login, their reset channel) to a child or a new person (security review 2026-10-30, a deferred minor).
Invented people and addresses. A comment above a test names the review it came from, if any."""

import re
from datetime import timedelta

from helpers import own_id, THROUGH_TUNNEL, add_person, login, make_person

from app import confirm_email, mailer, models
from app.timeutil import utcnow


# 9. An address counts only once a link mailed to it was opened: a parent can't hand someone else's address (their
# Cloudflare login, their reset channel) to a child or a new person
def person_named(client, name):
    return next(p for p in client.get("/api/people").json() if p["name"] == name)


def confirm_link_token(outbox) -> str:
    found = re.search(r"/confirm-email#token=([A-Za-z0-9_-]+)", outbox.mails[-1]["text"])
    assert found, outbox.mails[-1]["text"]
    return found.group(1)


def test_new_address_counts_after_confirmation(client, db, mail):
    login(client)
    added = add_person(client, "Lena", email="lena@example.org")
    assert (added["email"], added["email_pending"]) == (None, "lena@example.org")
    mailer.flush()
    assert mail.mails[-1]["to"] == ["lena@example.org"]
    token = confirm_link_token(mail)
    # Not yet a way back in
    client.post("/api/pin-reset", json={"name": "Lena"})
    mailer.flush()
    assert len(mail.mails) == 1
    assert client.post("/api/email-confirm", json={"token": token}).status_code == 200
    lena = person_named(client, "Lena")
    assert (lena["email"], lena["email_pending"]) == ("lena@example.org", None)
    again = client.post("/api/email-confirm", json={"token": token})
    assert again.status_code == 400 and again.json()["detail"] == "email_link_invalid"


def test_confirm_link_expires(client, db, mail):
    login(client)
    add_person(client, "Lena", email="lena@example.org")
    mailer.flush()
    db.query(models.EmailConfirm).update({models.EmailConfirm.expires_at: utcnow() - timedelta(minutes=1)})
    db.commit()
    assert client.post("/api/email-confirm", json={"token": confirm_link_token(mail)}).status_code == 400


def test_clearing_an_address_is_immediate(client, db, mail):
    login(client)
    lena = make_person(db, "Lena", email="lena@example.org")
    assert client.patch(f"/api/people/{lena.id}", json={"email": None}).json()["email"] is None


def test_address_taken_meanwhile(client, db, mail):
    login(client)
    add_person(client, "Lena", email="same@example.org")
    mailer.flush()
    lena_token = confirm_link_token(mail)
    add_person(client, "Max", email="same@example.org")
    mailer.flush()
    assert client.post("/api/email-confirm", json={"token": confirm_link_token(mail)}).status_code == 200
    taken = client.post("/api/email-confirm", json={"token": lena_token})
    assert taken.status_code == 409 and taken.json()["detail"] == "email_taken"


def test_confirm_not_through_the_tunnel(client, db, mail):
    login(client)
    add_person(client, "Lena", email="lena@example.org")
    mailer.flush()
    refused = client.post("/api/email-confirm", json={"token": confirm_link_token(mail)}, headers=THROUGH_TUNNEL)
    assert refused.status_code == 403


def test_nas_command_prints_a_confirm_link(client, db, configure, capsys):
    configure(HUB_PUBLIC_URL="https://home.local.example.ch")
    login(client)
    add_person(client, "Lena", email="lena@example.org")
    assert confirm_email.main(["Lena"]) == 0
    found = re.search(r"/confirm-email#token=([A-Za-z0-9_-]+)", capsys.readouterr().out)
    assert found
    assert client.post("/api/email-confirm", json={"token": found.group(1)}).status_code == 200
    assert confirm_email.main(["Max"]) == 1


def test_saving_again_with_the_waiting_address_changes_nothing(client, db, mail):
    login(client)
    me = client.get("/api/me").json()["id"]
    client.patch(f"/api/people/{me}", json={"email": "admin@example.org", "current_pin": "1234"})
    mailer.flush()
    sent = len(mail.mails)
    # The form sends the address it shows: the waiting one; no PIN needed, and no new mail
    again = client.patch(f"/api/people/{me}", json={"email": "admin@example.org", "color": "#123456"})
    mailer.flush()
    assert again.status_code == 200 and again.json()["email_pending"] == "admin@example.org"
    assert len(mail.mails) == sent


# Hub hardening (spec 2026-10-30), part 2
def test_own_email_needs_pin(client):
    login(client)
    me = own_id(client)
    missing = client.patch(f"/api/people/{me}", json={"email": "admin@example.org"})
    assert missing.status_code == 400 and missing.json()["detail"] == "pin_needed"
    wrong = client.patch(f"/api/people/{me}", json={"email": "admin@example.org", "current_pin": "0000"})
    assert wrong.status_code == 401 and wrong.json()["detail"] == "wrong_pin"
    right = client.patch(f"/api/people/{me}", json={"email": "admin@example.org", "current_pin": "1234"})
    assert right.status_code == 200 and right.json()["email_pending"] == "admin@example.org"
    lena = add_person(client, "Lena")
    assert client.patch(f"/api/people/{lena['id']}", json={"email": "lena@example.org"}).status_code == 200


# Second check (tests review 2026-11-07): a new address ends the old links, but even an open one only confirms the
# address that is still waiting
def test_a_link_confirms_only_the_waiting_address(client, db, mail):
    login(client)
    added = add_person(client, "Lena", email="lena@example.org")
    mailer.flush()
    lena = db.get(models.Person, added["id"])
    lena.email_pending = "other@example.org"
    db.commit()
    refused = client.post("/api/email-confirm", json={"token": confirm_link_token(mail)})
    assert refused.status_code == 400 and refused.json()["detail"] == "email_link_invalid"
    db.refresh(lena)
    assert lena.email is None
