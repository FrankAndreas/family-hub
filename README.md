# family-hub

The family's front door: one start page with a tile per app, and one family login that every family app accepts.
Self-hosted on a NAS next to the apps (family-budget-dashboard, family-chore, family-job-tracking, meal-planer, ...),
same stack and look. German by default, English per person.

- **People in one place**: name, e-mail address, PIN, parent or child, colour. Parents add family members and set PINs
  here only; each app keeps just its own details about a person.
- **At home** (`*.local.<domain>`): pick your name, type your PIN. The login cookie is set for `local.<domain>`, so
  every app at home gets it, for 30 days. Switching apps never asks again; logging out logs out of all apps.
- **From outside** (`*.<domain>` through the Cloudflare Tunnel): Cloudflare Access is the login (e-mail code or
  Google). The hub and the apps know the person by e-mail address. There is no PIN login outside, and the home cookie
  counts for nothing there.
- **Wrong PINs**: 5 in a row lock the person for 15 minutes, doubling up to a day. A browser the person logged in with
  before isn't locked by wrong PINs from other devices, so nobody at home can lock a parent out; its own wrong PINs
  count against it alone, and after 5 it is a device like any other.
- **Own PIN only**: each parent changes their own PIN and details and the children's; never another parent's. A
  forgotten PIN is reset with a link to the person's e-mail address, or from the NAS as the last resort.
- **Managing happens at home**: people, PINs and apps can't be changed from outside, so a mailbox someone broke into
  (past Cloudflare Access) can't take over the family's accounts.
- **Start page**: at home every app, linking to its home address; outside only the apps with an outside address. An
  app without a tunnel route is home-only, and its address never leaves the house.

Design: [docs/superpowers/specs/2026-10-29-family-hub-design.md](docs/superpowers/specs/2026-10-29-family-hub-design.md).
Running it on the NAS: [README_DOCKER.md](README_DOCKER.md).

## For apps: using the family login

An app that switches to the hub drops its own PINs and asks the hub who is logged in, with `GET <hub>/api/session`:

- **A request from outside** carries `Cf-Connecting-Ip` (Cloudflare sets it on everything through the tunnel). The app
  passes on that header and `Cf-Access-Jwt-Assertion`, **and never a `hub_session` cookie**: one arriving from outside
  can only be a stolen home login. The hub checks Cloudflare's token against Cloudflare's keys and the Access
  applications in its `CF_AUDIENCE`, so the app needs no Cloudflare settings of its own; with `Cf-Connecting-Ip` it
  ignores any hub token.
- **A request at home** (no `Cf-Connecting-Ip`) carries the hub's cookie `hub_session` (set for `local.<domain>`). The
  app passes it on as `Authorization: Bearer <hub_session>`.
- Neither header nor cookie belongs in an app's logs: each is a login to the hub, a parent's with full rights.

The answer is `{"valid": true, "person": {"id", "name", "email", "role", "color", "language"}}` or
`{"valid": false, "person": null}`. Cache it for a minute or so.

**Access per app.** In Einstellungen → Apps, an app that uses the family login gets a key (e.g. `budget`) and the
people who may use it; only they see its tile. The app asks `GET <hub>/api/session?app=<key>`: the answer adds
`"access": true|false`. `valid` stays about the login, so the app tells "not logged in" (send to the hub) from "no
access" (say so; sending them to the hub would bring them straight back, again and again).

**The app's people.** `GET <hub>/api/apps/<key>/people`, asked with the same login as `/api/session`, lists the active
people with access: `[{"id", "name", "role", "color", "language"}]` (no e-mail). 403 when the person asking has no
access, 404 for an unknown key. The app keeps its own copy keyed by `id`, refreshes it now and then, and hides people
who left the list instead of deleting their data. Logging out everywhere, a new PIN and deactivating a
person all end a login. The app keeps its own data per person under the hub's `person.id`.

The hub's tokens are EdDSA JWTs (`iss` `family-hub`, `sub` the person's id). An app may also check their signature
itself with the public key at `<hub>/.well-known/jwks.json`; asking `/api/session` is still what honours a logout.

Apps only read from the hub. Every change (POST, PUT, PATCH, DELETE) needs the header `X-Requested-With: hub`, which
the hub's own pages send: another page on the family's domain can make a browser send the login cookie, but not this
header.

Log out: send the person to `https://home.local.<domain>/logout?next=<the app's address>`. The hub ends that login
(for the hub and every app; `/api/session` says so within the app's cache time) and shows the login, which leads back
to the app. An app doesn't clear the cookie itself.

Managing the hub (people, PINs, apps) needs a second cookie, `hub_manage`, that only the hub's own address gets: a
`hub_session` an app passes on or leaks logs into the apps, but manages nothing.

Not logged in: send the person to `https://home.local.<domain>/?next=<the app's address>`. After the login the hub
sends them back, if the address belongs to an app on its start page.

## Development

```bash
python3 -m venv venv && venv/bin/pip install -r backend/requirements.txt -r tests/requirements.txt
venv/bin/pytest                       # backend tests
scripts/dev-backend.sh                # API on :8000 (COOKIE_INSECURE=1 for plain http)
cd frontend && npm install && npm run dev   # app on :5173, /api forwarded to :8000
cd e2e && npm install && E2E_PYTHON=../venv/bin/python npm test   # browser tests (e2e/README.md)
```

The repository is public: tests and docs use invented people and placeholders (`<domain>`, `<NAS_IP>`, `<team>`).

## License

MIT, see [LICENSE](LICENSE).
