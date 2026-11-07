# family-hub-client

The family apps' side of the hub's login (the hub's README, "For apps"), in one place instead of a copy per app:
asking the hub who is logged in (`/api/session`) and who may use the app (`/api/apps/<key>/people`), with the cache
and the rules for logins from outside. Standard library only. Each app keeps its own `auth.py` (where the login comes
from in a request, what a 401/403/503 looks like) and its own copy of the people, which depend on its data.

## Install

The apps' images have no git, so they install a GitHub archive of an exact commit (immutable), in
`backend/requirements.txt`:

```
family-hub-client @ https://github.com/FrankAndreas/family-hub/archive/<commit>.tar.gz#subdirectory=client
```

## Use

```python
# app/hub.py
from family_hub_client import HubClient, HubPerson, HubUnavailable, Login, Session, TIMEOUT_SECONDS  # noqa: F401

client = HubClient(default_app_key="budget")
```

- `client.session(Login(token))` at home (the `hub_session` cookie, or a Bearer token); from outside
  `Login(cf_access_jwt_assertion, outside_ip=cf_connecting_ip)`. Returns a `Session(person, access, renew)`, kept for a
  minute (only a valid login with access, and an invalid one at home; never "no access" or an outside "not logged
  in"). Raises `HubUnavailable` when the hub doesn't answer as expected: let nobody in then (503).
- `session.renew`: the hub login is in its last week. Send the browser once through
  `<public_url>/?next=<the page's address>`: the hub renews the login and sends it back. The family apps do it the
  same way: the backend's login dependency sets the response header `X-Hub-Renew: 1`, and the page, when it loads who
  is logged in, goes through the hub at most once a day (a time in `localStorage`; without storage not at all, so it
  can never loop).
- `client.fetch_people(login)`: the app's people (`[]` when the person asking may not ask); `HubPerson.email_shared`
  says whether the app's tile shares addresses (then `email` is the confirmed address or `None`).
- `client.hub_url()`, `client.public_url()`, `client.app_key()`: from `HUB_URL`, `HUB_PUBLIC_URL`, `HUB_APP_KEY`.
- `client.forget(login)` on logout; `client.forget()` in tests.

## Tests

`family_hub_client.fake.FakeHub` answers the client's requests as the hub does, and family-hub's own tests check that
it does (`tests/test_client.py`). In an app's `conftest.py`:

```python
fake = FakeHub(hub.client, on_change=hub_people.forget)
monkeypatch.setattr(hub.client, "transport", fake)
token = fake.add("Lena", role="CHILD")      # "tok-Lena"; cloudflare_token("Lena") from outside
```
