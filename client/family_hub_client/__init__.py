"""The family apps' side of the family hub's login (family-hub README, "For apps"): who is logged in, and the people
who may use the app.

The hub's login is a token: at home the `hub_session` cookie, passed to the hub as a Bearer token; from outside
Cloudflare Access's token, passed on with the visitor's Cf-Connecting-Ip. Neither is ever logged. Session answers are
kept for a minute, so a "log out everywhere" in the hub counts in the app within a minute. While the hub doesn't answer,
a login that had access within the last hour keeps it, so a restart of the hub doesn't throw everyone out."""

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Optional

__all__ = [
    "CACHE_SECONDS",
    "GRACE_SECONDS",
    "TIMEOUT_SECONDS",
    "HubClient",
    "HubPerson",
    "HubUnavailable",
    "Login",
    "Session",
    "Transport",
]

CACHE_SECONDS = 60
# How long a login with access keeps it while the hub doesn't answer (a restart or an update of the hub)
GRACE_SECONDS = 3600
TIMEOUT_SECONDS = 5
# Made-up logins are remembered only while fewer than this many answers are kept: a flood of them can't fill memory
MAX_REMEMBERED = 1000


@dataclass(frozen=True)
class HubPerson:
    id: int
    name: str
    role: str
    color: Optional[str]
    language: str
    # Only when the app's tile in the hub shares them: the confirmed address, or None
    email: Optional[str] = None
    email_shared: bool = False


class HubUnavailable(Exception):
    """The hub didn't answer, or not as expected: nobody is let in."""


@dataclass(frozen=True)
class Login:
    """A request's login. At home the hub's token; from outside (outside_ip: the visitor's Cf-Connecting-Ip) Cloudflare
    Access's token, which the hub checks against Cloudflare's keys and knows the person by their confirmed e-mail
    address. Where the request came from decides which it is, never the token's text."""

    token: str
    outside_ip: Optional[str] = None

    def headers(self) -> dict[str, str]:
        if self.outside_ip is not None:
            # With Cf-Connecting-Ip the hub takes only Cloudflare's token, whatever else came along
            return {"Cf-Access-Jwt-Assertion": self.token, "Cf-Connecting-Ip": self.outside_ip}
        return {"Authorization": f"Bearer {self.token}"}


@dataclass(frozen=True)
class Session:
    """Whose login it is (None: no valid login), whether they may use this app, and whether the hub login is in its
    last week (send the browser through the hub once, which renews it)."""

    person: Optional[HubPerson]
    access: bool
    renew: bool = False


# How a request reaches the hub: (path with query, headers) -> (HTTP status, JSON body or None). Raises HubUnavailable
# when there is no answer. Tests put family_hub_client.fake.FakeHub in its place
Transport = Callable[[str, dict[str, str]], tuple[int, object]]


def _person(data: dict) -> HubPerson:
    return HubPerson(
        id=int(data["id"]),
        name=str(data["name"]),
        role=str(data["role"]),
        color=data.get("color"),
        language=str(data.get("language") or "de"),
        email=str(data["email"]).strip().casefold() if data.get("email") else None,
        email_shared="email" in data,
    )


class HubClient:
    """The hub as one app sees it. Settings are read when used, from HUB_URL (how the backend reaches the hub, e.g.
    http://<NAS_IP>:8086), HUB_PUBLIC_URL (where browsers log in, e.g. https://home.local.<domain>) and HUB_APP_KEY
    (the app's key in the hub's Einstellungen → Apps). An empty setting counts as unset (docker-compose passes
    HUB_URL=${HUB_URL:-})."""

    def __init__(self, default_app_key: str, transport: Optional[Transport] = None):
        self.default_app_key = default_app_key
        self.transport: Transport = transport or self._http
        self._cache: dict[str, tuple[float, Session]] = {}
        # The hub's last "valid, with access" per login, for while it doesn't answer
        self._granted: dict[str, tuple[float, Session]] = {}
        self._lock = threading.Lock()

    def hub_url(self) -> str:
        return (os.getenv("HUB_URL") or "http://localhost:8086").rstrip("/")

    def public_url(self) -> str:
        return (os.getenv("HUB_PUBLIC_URL") or self.hub_url()).rstrip("/")

    def app_key(self) -> str:
        return os.getenv("HUB_APP_KEY") or self.default_app_key

    def _http(self, path: str, headers: dict[str, str]) -> tuple[int, object]:
        request = urllib.request.Request(f"{self.hub_url()}{path}", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # nosec B310 - the hub's URL
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, None
        except (urllib.error.URLError, OSError, ValueError) as error:
            # Only the kind of failure: keep messages short and free of request details (the headers carry the login)
            raise HubUnavailable(type(error).__name__) from None

    def fetch_session(self, login: Login) -> Session:
        """Asks the hub now: the person the login belongs to and whether they may use this app."""
        status, body = self.transport(f"/api/session?app={urllib.parse.quote(self.app_key())}", login.headers())
        if status != 200 or not isinstance(body, dict):
            raise HubUnavailable(f"session answered {status}")
        if not body.get("valid") or not body.get("person"):
            return Session(None, False)
        return Session(_person(body["person"]), bool(body.get("access")), bool(body.get("renew")))

    def fetch_people(self, login: Login) -> list[HubPerson]:
        """Everyone the hub lets use this app; [] when the login's person may not ask (no access or no login)."""
        status, body = self.transport(f"/api/apps/{urllib.parse.quote(self.app_key())}/people", login.headers())
        if status in (401, 403):
            return []
        if status != 200 or not isinstance(body, list):
            raise HubUnavailable(f"people answered {status}")
        return [_person(item) for item in body]

    @staticmethod
    def _key(login: Login) -> str:
        kind = "outside" if login.outside_ip is not None else "home"
        return hashlib.sha256(f"{kind}:{login.token}".encode()).hexdigest()

    def session(self, login: Login) -> Session:
        """fetch_session, kept for CACHE_SECONDS per login (keyed by a hash, never the token itself). Kept: a valid
        login with access, and no hub login at all (a made-up cookie costs no hub call on every request; such a token
        never becomes valid). Not kept: "no access", so someone given access a moment ago gets in at once; and "no
        login" from outside, which may be an address confirmed a moment ago or a hub that couldn't check Cloudflare's
        token.

        When the hub doesn't answer, a login it last answered "valid, with access" within GRACE_SECONDS keeps that
        answer, without `renew` (sending the browser to a hub that is down would strand it); any other login gets
        HubUnavailable. Only logins the hub confirmed are kept this way, so made-up ones can't fill memory. Nothing can
        be changed in the hub while it is down, so no logout or lost access is missed."""
        key = self._key(login)
        now = time.monotonic()
        with self._lock:
            for stale in [k for k, (at, _) in self._cache.items() if now - at >= CACHE_SECONDS]:
                del self._cache[stale]
            for stale in [k for k, (at, _) in self._granted.items() if now - at >= GRACE_SECONDS]:
                del self._granted[stale]
            if key in self._cache:
                return self._cache[key][1]
        try:
            found = self.fetch_session(login)
        except HubUnavailable:
            with self._lock:
                granted = self._granted.get(key)
            if granted is None:
                raise
            return replace(granted[1], renew=False)
        if found.person is not None:
            keep = found.access
        else:
            keep = login.outside_ip is None and len(self._cache) < MAX_REMEMBERED
        with self._lock:
            if keep:
                self._cache[key] = (now, found)
            if found.person is not None and found.access:
                self._granted[key] = (now, found)
            else:
                # The hub answered otherwise (logged out, access taken away): nothing left to fall back on
                self._granted.pop(key, None)
        return found

    def forget(self, login: Optional[Login] = None) -> None:
        """Drop the kept answers for one login (logging out), or all of them (tests)."""
        with self._lock:
            if login is None:
                self._cache.clear()
                self._granted.clear()
            else:
                self._cache.pop(self._key(login), None)
                self._granted.pop(self._key(login), None)
