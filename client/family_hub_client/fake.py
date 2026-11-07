"""A stand-in for the family hub in an app's tests: it answers the client's requests (HubClient.transport) as the hub
does, so the app's tests go through the real client. family-hub's tests check that the answers match the hub's
(tests/test_client.py).

Each person's hub token is "tok-<name>", and Cloudflare Access's token for them from outside "cf-<name>". Invented
people only: the repositories are public."""

import re
import urllib.parse
from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import Optional

from . import HubClient, HubPerson, HubUnavailable


def token(name: str) -> str:
    """The person's hub login (the `hub_session` cookie at home)."""
    return f"tok-{name}"


def cloudflare_token(name: str) -> str:
    """What Cloudflare Access sends as Cf-Access-Jwt-Assertion after the person's e-mail code (outside)."""
    return f"cf-{name}"


class FakeHub:
    """The hub with the people of one app. `down`: no answer (HubUnavailable). `share_email`: the app's tile shares the
    confirmed addresses (`emails`, by name). `renewing`: the names whose hub login is in its last week.

    Every change forgets what the client and the app kept (`on_change`, e.g. the app's hub_people.forget), so a test
    sees it at once."""

    def __init__(self, client: HubClient, on_change: Callable[[], None] | Iterable[Callable[[], None]] = ()):
        self.client = client
        self._on_change = [on_change] if callable(on_change) else list(on_change)
        self.people: dict[str, HubPerson] = {}
        self.access: set[str] = set()
        self.down = False
        self.share_email = False
        self.emails: dict[str, str] = {}
        self.renewing: set[str] = set()
        self._next_id = 1

    def _changed(self) -> None:
        self.client.forget()
        for forget in self._on_change:
            forget()

    def add(
        self,
        name: str,
        role: str = "PARENT",
        access: bool = True,
        language: str = "de",
        color: Optional[str] = None,
        id: Optional[int] = None,
    ) -> str:
        """A person in the hub (with access to the app unless access=False); returns their hub token."""
        if id is None:
            id = self._next_id
        self._next_id = max(self._next_id, id) + 1
        self.people[name] = HubPerson(id=id, name=name, role=role, color=color, language=language)
        if access:
            self.access.add(name)
        self._changed()
        return token(name)

    def give_access(self, name: str) -> None:
        self.access.add(name)
        self._changed()

    def remove_access(self, name: str) -> None:
        self.access.discard(name)
        self._changed()

    def rename(self, old: str, new: str) -> None:
        self.people[new] = replace(self.people.pop(old), name=new)
        for names in (self.access, self.renewing):
            if old in names:
                names.discard(old)
                names.add(new)
        if old in self.emails:
            self.emails[new] = self.emails.pop(old)
        self._changed()

    def set_role(self, name: str, role: str) -> None:
        self.people[name] = replace(self.people[name], role=role)
        self._changed()

    def set_language(self, name: str, language: str) -> None:
        self.people[name] = replace(self.people[name], language=language)
        self._changed()

    # What the hub answers

    def _caller(self, headers: dict[str, str]) -> Optional[HubPerson]:
        # Where the request came from decides which login counts: from outside only Cloudflare's
        if "Cf-Connecting-Ip" in headers:
            sent, known = headers.get("Cf-Access-Jwt-Assertion"), cloudflare_token
        else:
            scheme, _, sent = headers.get("Authorization", "").partition(" ")
            sent, known = (sent if scheme.lower() == "bearer" else None), token
        return next((p for name, p in self.people.items() if sent and known(name) == sent), None)

    def _json(self, person: HubPerson, with_email: bool) -> dict:
        found: dict = {"id": person.id, "name": person.name, "role": person.role, "color": person.color}
        found["language"] = person.language
        if with_email:
            found["email"] = self.emails.get(person.name)
        return found

    def __call__(self, path: str, headers: dict[str, str]) -> tuple[int, object]:
        if self.down:
            raise HubUnavailable("down")
        url = urllib.parse.urlsplit(path)
        query = urllib.parse.parse_qs(url.query)
        caller = self._caller(headers)
        ours = self.client.app_key()
        if url.path == "/api/session":
            if caller is None:
                return 200, {"valid": False, "person": None}
            app = query["app"][0] if "app" in query else None
            outside = "Cf-Connecting-Ip" in headers
            answer: dict = {
                "valid": True,
                "person": self._json(caller, self.share_email and app == ours),
                "renew": not outside and caller.name in self.renewing,
            }
            if app is not None:
                answer["access"] = app == ours and caller.name in self.access
            return 200, answer
        people_of = re.fullmatch(r"/api/apps/([^/]+)/people", url.path)
        if people_of:
            if caller is None:
                return 401, None
            if urllib.parse.unquote(people_of.group(1)) != ours:
                return 404, None
            if caller.name not in self.access:
                return 403, None
            listed = sorted((self.people[name] for name in self.access), key=lambda p: p.name.strip().casefold())
            return 200, [self._json(p, self.share_email) for p in listed]
        return 404, None
