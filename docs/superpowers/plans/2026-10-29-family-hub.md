# family-hub v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The hub itself: the family's people with PIN login at home, a signed login cookie every app can check, the
Cloudflare Access token outside, a tile start page, and its deployment on the NAS. Switching the apps over is a later
plan per app.

**Architecture:** FastAPI + SQLite + Alembic backend and React + Vite + Tailwind frontend, structured like meal-planer
(the newest sibling): `backend/app`, `frontend/src`, `tests/`, `e2e/`, Docker (backend + nginx frontend), the same
`scripts/deploy-nas.sh` / `nas-update.sh`, CI workflows and Dependabot. The hub signs login tokens with an Ed25519 key
kept in `DATA_DIR`; its public key is served as a JWKS so apps verify without a shared secret.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2, Alembic, PyJWT[crypto], bcrypt; React 19, TS, Vite, Tailwind,
react-i18next; pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-29-family-hub-design.md`

## Global Constraints

- Public repository: invented names and e-mail addresses only (`mama@example.ch`, `Lena`); docs use `<domain>`,
  `<NAS_IP>`, `<team>`.
- Login cookie `hub_session`: `Domain=$COOKIE_DOMAIN` (e.g. `local.<domain>`; unset → host-only for dev), `HttpOnly`,
  `Secure` unless `COOKIE_INSECURE=1` (dev/tests), `SameSite=Lax`, 30 days.
- Token: EdDSA JWT `{iss: "family-hub", sub: "<person id>", ver: <token_version>, exp}`; `kid` in the header; key file
  `DATA_DIR/signing-key.pem` made on first start; JWKS at `GET /api/keys` (and `/.well-known/jwks.json`).
- A request "came through the tunnel" when it has the header `Cf-Connecting-Ip` (Cloudflare sets it; the DSM proxy
  doesn't). Then: PIN login refused (403 `login_at_home_only`), the cookie is ignored, only a valid Cloudflare Access
  token counts.
- Cloudflare: `CF_TEAM_DOMAIN` (e.g. `<team>.cloudflareaccess.com`) and `CF_AUDIENCE` (the hub's Access application
  AUD); certs from `https://$CF_TEAM_DOMAIN/cdn-cgi/access/certs`, cached 1 h; person by e-mail (case-insensitive).
  Unset → outside requests are 401.
- PIN: 4 digits; lockout like meal-planer (5 wrong → 15 min, doubling, max 1 day); first start makes parent "Admin"
  with `INITIAL_ADMIN_PIN` or a random PIN logged once.
- German default, English per person; every text in both locale files.
- Port `${PORT:-8086}` on the NAS.

## Review Focus

- A request through the tunnel that carries a valid home cookie → not logged in (cookie ignored). (Task 2 test)
- A Cloudflare token for an e-mail no person has, or an inactive person → 401, never a new person. (Task 4 test)
- A token signed by another key, expired, or after "log out everywhere" → `/api/session` says invalid. (Task 3 test)
- The last active parent can't be made a child, deactivated or locked out of managing people. (Task 5 test)
- A tile without an outside address is not shown (nor its address leaked) to a request through the tunnel. (Task 6 test)

---

### Task 1: Scaffold

Copy meal-planer's skeleton and strip it to the hub: `backend/app/{config,database,database_setup,errors,timeutil,
main}.py`, migrations env, `backend/Dockerfile`, `requirements.txt` (+ `PyJWT[crypto]`), `frontend/` build setup
(Dockerfile, nginx.conf with `/api` and `/.well-known` proxied, security headers, Vite, Tailwind, eslint, i18n),
`tests/conftest.py` + `helpers.py`, `pyproject.toml`, `pytest.ini`, `.github/` (workflows, dependabot), `.gitignore`,
`LICENSE` (MIT, Andreas Frank), `docker-compose.yml` (hub-backend / hub-frontend, port 8086), `.env.example`,
`scripts/{deploy-nas,nas-update,dev-backend}.sh` with names changed. Migration `0001_people` (people, tiles).

- [ ] `tests/test_health.py::test_health` (GET /health → ok) and `test_migrations.py::test_head_matches_models`
  first; FAIL; scaffold; PASS; frontend `npm run lint && npm run build` pass. Commit `chore: scaffold family-hub`.

### Task 2: People and the home login

**Produces:** `models.Person` (id, name, name_key unique, email nullable unique-ignoring-case, pin_hash, role
PARENT/CHILD, active, color, language, failed_logins, lockouts, locked_until, token_version, created_at);
`auth.authenticate`, `auth.issue_token(person) -> str`, `auth.current_person(request, db) -> Person` (cookie at home,
Cloudflare outside — Task 4 plugs in); `POST /api/login {name, pin}` (sets cookie), `POST /api/logout` (clears it),
`POST /api/logout-everywhere`, `GET /api/me`, `GET /api/people/public` (names + colours for the login screen; home only).

- [ ] Tests first: login sets the cookie with the constraints above; wrong PIN / lockout; inactive person can't log in;
  logout clears; logout-everywhere ends older tokens; tunnel request: login 403, cookie ignored, people/public 403.
  FAIL → implement → PASS. Commit `feat: people and the PIN login at home`.

### Task 3: Signing keys and the session check for apps

**Produces:** `keys.load_or_create(data_dir) -> (private_key, kid)`; `GET /api/keys` / `/.well-known/jwks.json`
(OKP Ed25519 JWK); `GET /api/session` with the token as `Authorization: Bearer` or the cookie → `{valid, person:
{id, name, email, role, color, language}}` (apps call it, caching briefly, to honour logout-everywhere and
deactivation).

- [ ] Tests first: key made once and reused across restarts; JWKS verifies a hub token (PyJWT + `PyJWK`); another
  key's token, an expired one, one with an old `ver`, an inactive person → `valid: false`. FAIL → implement → PASS.
  Commit `feat: signed logins apps can check`.

### Task 4: Cloudflare Access outside

**Produces:** `cloudflare.person_for(request, db) -> Person | None`: verifies `Cf-Access-Jwt-Assertion` (RS256,
issuer `https://$CF_TEAM_DOMAIN`, audience `CF_AUDIENCE`) with the cached certs, finds the active person by e-mail.

- [ ] Tests first with a test RSA key served as fake certs (monkeypatched fetch): valid token → `/api/me` is the
  person; unknown e-mail / inactive / wrong audience / expired / not configured → 401; certs fetched once per hour.
  FAIL → implement → PASS. Commit `feat: Cloudflare Access login from outside`.

### Task 5: Managing people (parents)

**Produces:** `GET /api/people`, `POST /api/people`, `PATCH /api/people/{id}` (name, email, role, active, color,
language), `PUT /api/people/{id}/pin` (parent for anyone; anyone for themselves via `PUT /api/me/pin` with the old
PIN), `PATCH /api/me` (language). Name and e-mail unique ignoring case. A new PIN or deactivation raises token_version.

- [ ] Tests first: parents only; unique name/e-mail; last active parent protected (no child, no deactivate); own PIN
  needs the old one; invented data only. FAIL → implement → PASS. Commit `feat: managing the family's people`.

### Task 6: Tiles

**Produces:** `models.Tile` (id, name, icon, local_url, remote_url nullable = home only, position);
`GET /api/tiles` (logged-in; at home: all, linking local_url; through the tunnel: only tiles with remote_url, linking
it; never the other address); parents: `POST/PATCH/DELETE /api/tiles`, `PUT /api/tiles/order`.

- [ ] Tests first: filtering and the link per side; parents only for changes; URLs must be https (http allowed for
  `localhost` in dev). FAIL → implement → PASS. Commit `feat: the start page's tiles`.

### Task 7: Frontend

Login page (names as tiles with colour, PIN pad from meal-planer's PinInput; outside: "Signed in with Cloudflare as
…" or "Not in the family list"), start page (tile grid, phone width), settings (people, tiles, own PIN, language,
log out / log out everywhere), DE/EN. Layout like the siblings.

- [ ] E2E first (`e2e/tests/hub.spec.ts`, Playwright like meal-planer): Admin logs in, adds a person and a tile, the
  start page shows the tile, logs out; the person logs in with their PIN; phone width 390 px. FAIL → implement →
  lint, type-check, build, e2e PASS. Commit `feat: start page, login and settings`.

### Task 8: Deployment docs

`README.md` (what it is, how apps use it: JWKS, `/api/session`, cookie, Cloudflare token) and `README_DOCKER.md`:
NAS folder `/volume1/docker/family-hub`, `.env` (`SECRET`-free: key file in data), DSM reverse proxy
`home.local.<domain>` → `localhost:8086`, `COOKIE_DOMAIN=local.<domain>`, Cloudflare tunnel route `home.<domain>` +
Access application (family policy) + `CF_TEAM_DOMAIN` / `CF_AUDIENCE`, backups. Commit `docs: running family-hub on
the NAS`.
