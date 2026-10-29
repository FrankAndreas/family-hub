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
- **Start page**: at home every app, linking to its home address; outside only the apps with an outside address. An
  app without a tunnel route is home-only, and its address never leaves the house.

Design: [docs/superpowers/specs/2026-10-29-family-hub-design.md](docs/superpowers/specs/2026-10-29-family-hub-design.md).
Running it on the NAS: [README_DOCKER.md](README_DOCKER.md).

## For apps: using the family login

An app that switches to the hub drops its own PINs and asks the hub who is logged in:

- **At home** the browser sends the hub's cookie `hub_session` to the app (it is set for `local.<domain>`). The app
  passes it on: `GET <hub>/api/session` with `Authorization: Bearer <hub_session>`.
- **From outside** Cloudflare adds `Cf-Access-Jwt-Assertion` to every request. The app passes that header on to the
  same `GET <hub>/api/session`. The hub checks it against Cloudflare's keys and the Access applications listed in its
  `CF_AUDIENCE`, so the app needs no Cloudflare settings of its own.

The answer is `{"valid": true, "person": {"id", "name", "email", "role", "color", "language"}}` or
`{"valid": false, "person": null}`. Cache it for a minute or so. Logging out everywhere, a new PIN and deactivating a
person all end a login. The app keeps its own data per person under the hub's `person.id`.

The hub's tokens are EdDSA JWTs (`iss` `family-hub`, `sub` the person's id). An app may also check their signature
itself with the public key at `<hub>/.well-known/jwks.json`; asking `/api/session` is still what honours a logout.

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
