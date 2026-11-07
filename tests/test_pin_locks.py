"""Wrong PINs lock the person: 5 in a row for 15 minutes, doubling. A browser the person logged in with before isn't
locked by other devices' wrong PINs. Invented people. A comment above a test names the review it came from, if any."""

import threading
import time

from fastapi.testclient import TestClient
from helpers import ADMIN, ADMIN_PIN, APP_HEADER, add_person, device, login, set_cookie

from app import models, pins
from app.main import app


def wrong_pins(client, name=ADMIN, times=pins.MAX_FAILED_LOGINS):
    for _ in range(times):
        assert client.post("/api/login", json={"name": name, "pin": "0000"}).status_code == 401


def try_login(client, name=ADMIN, pin=ADMIN_PIN) -> int:
    return client.post("/api/login", json={"name": name, "pin": pin}).status_code


def test_wrong_pin_and_lockout(client):
    for _ in range(4):
        assert client.post("/api/login", json={"name": "admin", "pin": "0000"}).status_code == 401
    assert client.post("/api/login", json={"name": "Admin", "pin": "0000"}).status_code == 401
    # Locked now, even with the right PIN
    response = client.post("/api/login", json={"name": "Admin", "pin": ADMIN_PIN})
    assert response.status_code == 429 and response.json()["detail"]["code"] == "locked"


# Security review 2026-10-29
def test_parallel_wrong_pins_count_every_try(monkeypatch):
    # Many guesses at once: each one counts, so no more than the allowed few get an answer before the lock
    real = pins.verify_pin

    def slow(pin, hashed):
        time.sleep(0.05)
        return real(pin, hashed)

    monkeypatch.setattr(pins, "verify_pin", slow)
    codes: list[int] = []

    def guess(n):
        response = TestClient(app, headers=APP_HEADER).post("/api/login", json={"name": "Admin", "pin": f"{n:04d}"})
        codes.append(response.status_code)

    threads = [threading.Thread(target=guess, args=(n,)) for n in range(2000, 2020)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert codes.count(401) <= pins.MAX_FAILED_LOGINS
    assert codes.count(429) == len(codes) - codes.count(401)


# Security review 2026-10-29
def test_own_pin_change_counts_wrong_old_pins(client):
    login(client)
    for _ in range(pins.MAX_FAILED_LOGINS):
        assert client.put("/api/me/pin", json={"old_pin": "0000", "pin": "1357"}).status_code == 401
    locked = client.put("/api/me/pin", json={"old_pin": ADMIN_PIN, "pin": "1357"})
    assert locked.status_code == 429


# Known devices. Security review 2026-10-30, finding 1: anyone at home could lock every parent out with wrong PINs


def test_wrong_pins_elsewhere_dont_lock_a_known_device(client):
    login(client)
    client.post("/api/logout")
    other = device()
    wrong_pins(other)
    assert try_login(other) == 429
    assert try_login(client) == 200


def test_a_known_device_gets_a_few_tries_of_its_own(client):
    login(client)
    client.post("/api/logout")
    wrong_pins(client)
    # Its wrong PINs didn't count against the person
    assert try_login(device()) == 200
    # Now it is a device like any other: its wrong PINs count, and lock the person
    wrong_pins(client)
    assert try_login(client) == 429


def test_a_device_is_known_per_person(client):
    login(client)
    add_person(client, "Lena", pin="5678")
    tablet = device()
    login(tablet, "Lena", "5678")
    tablet.post("/api/logout")
    wrong_pins(device())
    assert try_login(tablet) == 429


def test_a_correct_login_on_a_known_device_lifts_the_lock(client):
    login(client)
    client.post("/api/logout")
    wrong_pins(device())
    assert try_login(client) == 200
    assert try_login(device()) == 200


def test_the_device_cookie_stays_with_the_hub(client, configure):
    configure(COOKIE_DOMAIN="local.example.ch")
    response = login(client)
    header = set_cookie(response, "hub_device")
    # Other apps at home get the login cookie, never this one
    assert "Domain=" not in header
    assert "HttpOnly" in header and "SameSite=strict" in header


def test_known_devices_are_capped(client, db):
    for _ in range(pins.MAX_DEVICES + 5):
        login(device())
    assert db.query(models.KnownDevice).count() == pins.MAX_DEVICES
