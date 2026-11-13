"""The apps' client package (client/, app integration review 2026-11-07): the same requests answered by the hub and by
the fake hub the apps test with, so the fake can't drift from the hub; and the client's own rules (HTTP, cache)."""

import json
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import family_hub_client
import pytest
from family_hub_client import CACHE_SECONDS, GRACE_SECONDS, HubClient, HubUnavailable, Login, Session
from family_hub_client.fake import FakeHub, cloudflare_token
from family_hub_client.fake import token as fake_token
from helpers import budget_tile, make_person, token

from app import auth

PATHS = [
    "/api/session",
    "/api/session?app=budget",
    "/api/session?app=nope",
    "/api/apps/budget/people",
    "/api/apps/nope/people",
]


def _real(client):
    def transport(path, headers):
        answer = client.get(path, headers=headers)
        return answer.status_code, answer.json() if answer.status_code == 200 else None

    return transport


@pytest.mark.parametrize("share_email", [False, True])
def test_the_fake_answers_as_the_hub(client, db, access, monkeypatch, share_email):
    # In neither order of their ids: the list is by name, regardless of case
    mama = make_person(db, "Mama", role="PARENT", email="mama@example.ch", color="#f59e0b")
    anna = make_person(db, "anna")
    lena = make_person(db, "Lena", email="lena@example.org")
    max_ = make_person(db, "Max")
    budget_tile(db, mama, anna, lena).share_email = share_email
    db.commit()
    fake = FakeHub(HubClient("budget"))
    fake.add("Mama", role="PARENT", color="#f59e0b", id=mama.id)
    fake.add("anna", role="CHILD", id=anna.id)
    fake.add("Lena", role="CHILD", id=lena.id)
    fake.add("Max", role="CHILD", access=False, id=max_.id)
    fake.emails = {"Mama": "mama@example.ch", "Lena": "lena@example.org"}
    fake.share_email = share_email
    fake.renewing = {"Lena"}
    hub_logins = {"Mama": auth.issue_tokens(mama)[0], "Max": auth.issue_tokens(max_)[0]}
    # Lena's login is in its last week
    monkeypatch.setattr(auth, "TOKEN_LIFETIME", timedelta(days=3))
    hub_logins["Lena"] = auth.issue_tokens(lena)[0]

    callers = [(Login(hub_logins[name]), Login(fake_token(name))) for name in ("Mama", "Lena", "Max")]
    callers += [(Login("made-up"), Login("made-up"))]
    # From outside: Cloudflare's token, and a hub token there counts for nothing
    callers += [
        (Login(token(email), "203.0.113.7"), Login(cloudflare_token(name), "203.0.113.7"))
        for name, email in (("Mama", "mama@example.ch"), ("Lena", "lena@example.org"))
    ]
    callers += [(Login(hub_logins["Mama"], "203.0.113.7"), Login(fake_token("Mama"), "203.0.113.7"))]
    real = _real(client)
    for real_login, fake_login in callers:
        for path in PATHS:
            assert fake(path, fake_login.headers()) == real(path, real_login.headers()), (path, fake_login)


def test_the_client_reads_the_hubs_answers(client, db, access):
    lena = make_person(db, "Lena", email="lena@example.org", color="#123456")
    budget_tile(db, lena).share_email = True
    db.commit()
    hub = HubClient("budget", transport=_real(client))
    login = Login(auth.issue_tokens(lena)[0])
    found = hub.fetch_session(login)
    assert found.access is True and found.renew is False
    assert (found.person.id, found.person.name, found.person.role) == (lena.id, "Lena", "CHILD")
    assert (found.person.color, found.person.email, found.person.email_shared) == ("#123456", "lena@example.org", True)
    assert [p.name for p in hub.fetch_people(login)] == ["Lena"]
    assert hub.fetch_session(Login("made-up")) == Session(None, False)
    assert hub.fetch_people(Login("made-up")) == []
    assert hub.fetch_session(Login(token("lena@example.org"), "203.0.113.7")).person.name == "Lena"
    assert HubClient("nope", transport=_real(client)).fetch_session(login).access is False
    with pytest.raises(HubUnavailable):
        HubClient("nope", transport=_real(client)).fetch_people(login)


class _Counting:
    def __init__(self, fake):
        self.fake, self.calls = fake, 0

    def __call__(self, path, headers):
        self.calls += 1
        return self.fake(path, headers)


def test_what_the_client_keeps():
    hub = HubClient("budget")
    fake = FakeHub(hub)
    hub.transport = counting = _Counting(fake)
    lena = Login(fake.add("Lena", role="CHILD"))
    max_ = Login(fake.add("Max", role="CHILD", access=False))

    def asks(login):
        before = counting.calls
        hub.session(login)
        return counting.calls - before

    # A valid login with access, and a made-up one at home: asked once a minute
    assert (asks(lena), asks(lena)) == (1, 0)
    assert (asks(Login("made-up")), asks(Login("made-up"))) == (1, 0)
    # "No access" (maybe given a moment later) and "not logged in" from outside (maybe confirmed a moment later): always
    assert (asks(max_), asks(max_)) == (1, 1)
    assert (asks(Login("made-up", "203.0.113.7")), asks(Login("made-up", "203.0.113.7"))) == (1, 1)
    # The same token from outside is another login
    assert asks(Login(fake_token("Lena"), "203.0.113.7")) == 1
    hub.forget(lena)
    assert asks(lena) == 1


def test_a_hub_that_is_down_keeps_logins_with_access_for_a_while(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(family_hub_client.time, "monotonic", lambda: clock[0])
    hub = HubClient("budget")
    fake = FakeHub(hub)
    hub.transport = fake
    lena = Login(fake.add("Lena", role="CHILD"))
    max_ = Login(fake.add("Max", role="CHILD", access=False))
    fake.renewing = {"Lena"}
    assert hub.session(lena).renew
    hub.session(max_)
    fake.down = True

    # Past the minute the hub is asked again and doesn't answer: Lena keeps her access, without the trip to the hub
    clock[0] += CACHE_SECONDS
    kept = hub.session(lena)
    assert kept.person is not None and kept.person.name == "Lena"
    assert kept.access and not kept.renew
    # Nobody else gets in: neither a login without access, nor one the hub never confirmed
    for login in (max_, Login("made-up"), Login(fake_token("Lena"), "203.0.113.7")):
        with pytest.raises(HubUnavailable):
            hub.session(login)
    # Not for longer than the grace time since the hub last confirmed it
    clock[0] = 1000.0 + GRACE_SECONDS
    with pytest.raises(HubUnavailable):
        hub.session(lena)


def test_what_the_hub_answered_last_ends_the_grace(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(family_hub_client.time, "monotonic", lambda: clock[0])
    hub = HubClient("budget")
    fake = FakeHub(hub)
    hub.transport = fake
    lena = Login(fake.add("Lena", role="CHILD"))
    hub.session(lena)
    # Access taken away (behind the client's back, so only the hub's next answer tells it), then the hub goes down
    fake.access.discard("Lena")
    clock[0] += CACHE_SECONDS
    assert not hub.session(lena).access
    fake.down = True
    with pytest.raises(HubUnavailable):
        hub.session(lena)
    # Logging out forgets the grace too
    fake.down = False
    fake.access.add("Lena")
    hub.session(lena)
    hub.forget(lena)
    fake.down = True
    with pytest.raises(HubUnavailable):
        hub.session(lena)


def test_the_fake_tells_the_app_what_changed():
    hub = HubClient("budget")
    forgotten = []
    fake = FakeHub(hub, on_change=lambda: forgotten.append(True))
    hub.transport = fake
    lena = Login(fake.add("Lena", role="CHILD"))
    assert hub.session(lena).person.role == "CHILD"
    fake.set_role("Lena", "PARENT")
    assert hub.session(lena).person.role == "PARENT" and forgotten
    fake.rename("Lena", "Lea")
    assert hub.session(Login(fake_token("Lea"))).person.name == "Lea"
    fake.down = True
    with pytest.raises(HubUnavailable):
        hub.session(lena)


class _Hub(BaseHTTPRequestHandler):
    """A hub on a real port: answers what `answers` holds for the path, and keeps the headers it got."""

    answers: dict[str, tuple[int, bytes]] = {}
    seen: list[dict] = []

    def do_GET(self):
        type(self).seen.append(dict(self.headers))
        status, body = self.answers.get(self.path, (404, b"{}"))
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def http_hub(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Hub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("HUB_URL", f"http://127.0.0.1:{server.server_address[1]}/")
    _Hub.answers, _Hub.seen = {}, []
    yield _Hub
    server.shutdown()
    server.server_close()


def test_the_client_over_http(http_hub, monkeypatch):
    person = {"id": 7, "name": "Lena", "role": "CHILD", "color": None, "language": "en"}
    http_hub.answers = {
        "/api/session?app=budget": (200, json.dumps({"valid": True, "person": person, "access": True}).encode()),
        "/api/apps/budget/people": (403, b'{"detail": "no_access"}'),
    }
    hub = HubClient("budget")
    found = hub.fetch_session(Login("tok"))
    assert found.person.language == "en" and found.person.email_shared is False and found.renew is False
    assert http_hub.seen[-1]["Authorization"] == "Bearer tok"
    hub.fetch_session(Login("cf", "203.0.113.7"))
    assert "Authorization" not in http_hub.seen[-1]
    assert (http_hub.seen[-1]["Cf-Access-Jwt-Assertion"], http_hub.seen[-1]["Cf-Connecting-Ip"]) == (
        "cf",
        "203.0.113.7",
    )
    assert hub.fetch_people(Login("tok")) == []
    # The app's key from its setting
    monkeypatch.setenv("HUB_APP_KEY", "money")
    with pytest.raises(HubUnavailable, match="404"):
        hub.fetch_session(Login("tok"))
    # Not the hub's JSON, or no hub at all
    monkeypatch.delenv("HUB_APP_KEY")
    http_hub.answers["/api/session?app=budget"] = (200, b"<html>")
    with pytest.raises(HubUnavailable):
        hub.fetch_session(Login("tok"))
    monkeypatch.setenv("HUB_URL", "http://127.0.0.1:9")
    with pytest.raises(HubUnavailable) as raised:
        hub.fetch_session(Login("secret-token"))
    assert "secret-token" not in str(raised.value)


def test_the_addresses_from_the_settings(monkeypatch):
    hub = HubClient("budget")
    for name in ("HUB_URL", "HUB_PUBLIC_URL", "HUB_APP_KEY"):
        monkeypatch.setenv(name, "")
    assert (hub.hub_url(), hub.public_url(), hub.app_key()) == (
        "http://localhost:8086",
        "http://localhost:8086",
        "budget",
    )
    monkeypatch.setenv("HUB_URL", "http://192.0.2.5:8086/")
    monkeypatch.setenv("HUB_PUBLIC_URL", "https://home.local.example.ch/")
    assert (hub.hub_url(), hub.public_url()) == ("http://192.0.2.5:8086", "https://home.local.example.ch")
