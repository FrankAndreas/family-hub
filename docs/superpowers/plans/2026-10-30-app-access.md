# App Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parents set per app who may use it; the start page shows each person their apps; apps can ask whether a
login has access and pull their people.

**Architecture:** A tile gets an optional `app_key` and a set of people (`tile_access`). `/api/tiles` filters by
access; `/api/session?app=<key>` adds `access`; `/api/apps/<key>/people` lists the people with access.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, React 19/TS, Playwright (as in the repo).

**Spec:** Part A of `docs/superpowers/specs/2026-10-30-hub-login-design.md` in FrankAndreas/family-budget-dashboard
(local: `/home/andreas/work/family-budget-dashboard/docs/superpowers/specs/2026-10-30-hub-login-design.md`).

## Global Constraints

- Management stays home-only and parents only (`auth.require_parent`, which already requires home).
- Tests and docs use invented people and placeholders (`<domain>`, `<NAS_IP>`); the repo is public.
- No token or cookie value in any log line.
- Checks: `venv/bin/pytest`, black, flake8 (`--max-line-length=120 --extend-ignore=E203,W503`), mypy; frontend
  `npm run lint && npm run type-check && npm run build && npx vitest run`; e2e `cd e2e && E2E_PYTHON=../.superpowers/venv/bin/python npm test`.

**Plan ruling (deviation from the spec, A.4):** the spec says `/api/session?app=<key>` answers `valid: false` without
access. Then an app can't tell "not logged in" (send to the hub) from "no access" (say so): sending a logged-in person
without access to the hub, which sends them back, loops. So: with `app`, the answer keeps `valid` about the login and
adds `"access": true|false`. Cost if wrong: one field.

## Review Focus

- A tile key changed or removed while apps use it: `/api/apps/<old>/people` answers 404; the tile's access list stays
  with the tile. Test in Task 1.
- A deactivated person with access: not in `/api/apps/<key>/people`, `/api/session` invalid as today. Test in Task 2.
- A tile without a key: shown to everyone, access ignored; `/api/session?app=` with an unknown key → `access: false`.
  Test in Task 2.
- Through the tunnel: `/api/apps/<key>/people` with the Cloudflare token works like `/api/session` (outside rules,
  no Bearer). Test in Task 2.
- Two tiles given the same key: 409 `app_key_taken`, nothing saved. Test in Task 1.

---

### Task 1: App key and access on tiles

**Files:**
- Modify: `backend/app/models.py` (Tile: `app_key`, relationship `people`; new table `tile_access`)
- Create: `backend/app/migrations/versions/0002_app_access.py`
- Modify: `backend/app/schemas.py` (TileIn, TilePatch, TileOut), `backend/app/tiles_api.py`, `backend/app/errors.py`
  if messages live there
- Test: `tests/test_tiles.py`

**Interfaces:**
- Produces: `models.Tile.app_key: str | None` (String(20), unique), `models.Tile.people: list[models.Person]`
  (secondary `tile_access` with `tile_id`, `person_id`, both FKs `ondelete="CASCADE"`, composite PK, named
  constraints like 0001). Schemas: `TileIn.app_key: str | None` (pattern `^[a-z][a-z0-9-]{1,19}$`),
  `TileIn.people: list[int] = []`; `TilePatch` the same, optional; `TileOut.app_key`, `TileOut.people: list[int]`
  (ids, sorted).

- [ ] **Step 1: Write the failing tests** in `tests/test_tiles.py`:
  - `test_tile_keeps_key_and_people`: parent adds `{**BUDGET, "app_key": "budget", "people": [lena_id]}` → 201,
    `/api/tiles/manage` shows `app_key == "budget"`, `people == [lena_id]`; PATCH `{"people": []}` → `people == []`;
    PATCH `{"app_key": None}` → key removed.
  - `test_app_key_unique`: second tile with `app_key: "budget"` → 409, `detail` code `app_key_taken`; tile count
    unchanged.
  - `test_app_key_format`: `"Budget"`, `"b"`, `"budget app"` → 422.
  - `test_access_unknown_person`: `people: [9999]` → 400 `person_not_found`.
- [ ] **Step 2: Run** `venv/bin/pytest tests/test_tiles.py -q` — Expected: the four new tests FAIL.
- [ ] **Step 3: Implement** model, migration 0002 (down_revision `0001`; `test_migration_matches_models` and
  `test_constraints_are_named` must stay green), schemas and the add/change routes (resolve ids to active or inactive
  people; unknown → 400; duplicate key → 409 via a check before commit, not by catching the DB error).
- [ ] **Step 4: Run** `venv/bin/pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `feat: app key and access per tile`.

### Task 2: Start page, session and people per app

**Files:**
- Modify: `backend/app/tiles_api.py`, `backend/app/session_api.py`
- Create: `backend/app/apps_api.py` (router registered in `main.py`)
- Test: `tests/test_tiles.py`, `tests/test_session.py`, create `tests/test_apps.py`

**Interfaces:**
- Consumes: Task 1's `Tile.app_key`, `Tile.people`.
- Produces: `session_api.caller(request, credentials, db) -> models.Person | None` (the existing person lookup of
  `/api/session`, extracted, reused by apps_api). `GET /api/session?app=<key>` → as today plus `"access": bool` when
  `app` is given (false for an unknown key or a tile without the person). `GET /api/apps/{key}/people` →
  `[{"id", "name", "role", "color", "language"}]` of active people with access, ordered by name; 401 without a valid
  caller, 404 `app_not_found` for an unknown key, 403 `no_access` when the caller isn't on the list.
  `/api/tiles`: tiles without a key, plus keyed tiles listing the person.

- [ ] **Step 1: Write the failing tests:**
  - `test_tiles.py::test_start_page_shows_own_apps`: tiles Budget (key `budget`, people [Admin]) and Essen (no key);
    Admin sees both; Lena sees only Essen.
  - `test_session.py::test_session_access_per_app`: with Lena's token, `?app=budget` → `valid: true`,
    `access: false`; after adding her → `access: true`; `?app=nope` → `access: false`; without `app` no `access` key.
  - `test_apps.py::test_people_of_an_app`: Admin and Lena on `budget`, Max not: Admin's Bearer token →
    `[Admin, Lena]` with exactly the keys `id, name, role, color, language` (no `email`); Max's token → 403;
    `/api/apps/nope/people` → 404; no token → 401.
  - `test_apps.py::test_inactive_people_left_out`: Lena on `budget`, then deactivated → not in Admin's list.
  - `test_apps.py::test_people_from_outside`: with the `access` fixture from `test_cloudflare`, a parent with e-mail
    on `budget` gets the list with `outside(token())` headers; a Bearer token through the tunnel → 401.
- [ ] **Step 2: Run** `venv/bin/pytest tests/test_tiles.py tests/test_session.py tests/test_apps.py -q` — Expected:
  new tests FAIL.
- [ ] **Step 3: Implement** `caller()`, the `access` field, `apps_api.py`, the `/api/tiles` filter (outside rules
  unchanged: still only tiles with `remote_url` outside).
- [ ] **Step 4: Run** `venv/bin/pytest -q` plus black/flake8/mypy — Expected: all pass, clean.
- [ ] **Step 5: Commit** `feat: apps ask for access and their people`.

### Task 3: Access in Einstellungen, docs

**Files:**
- Modify: `frontend/src/components/TilesSettings.tsx`, `frontend/src/types.ts`, `frontend/src/locales/{de,en}.ts`
- Modify: `e2e/tests/hub.spec.ts`, `README.md` ("For apps"), `README_DOCKER.md` (adding an app: key and access)

**Interfaces:**
- Consumes: Task 1's tile fields; the people list the settings already load (`/api/people`).

- [ ] **Step 1: Write the failing e2e test** in `hub.spec.ts`, `test('access per app')`: Admin adds person
  `uniqueName('Mia')`, adds app `uniqueName('Geld')` with key field `App key` = a unique key
  (`k` + 6 lowercase chars) and ticks only Admin under `Who may use it`; logs out (wait for "Who are you?"),
  logs in as Mia: the tile is not there; the existing test's keyless tile still is.
- [ ] **Step 2: Run** `cd e2e && E2E_PYTHON=../.superpowers/venv/bin/python npx playwright test hub.spec.ts` —
  Expected: FAIL (no `App key` field).
- [ ] **Step 3: Implement** in the tile form: text input `App key` (en) / `App-Schlüssel` (de), hint "only for apps
  that use the family login" / "nur für Apps mit dem Familien-Login"; checkboxes of active people under
  `Who may use it` / `Wer darf sie nutzen`, shown only when a key is set; the list row shows the number of people
  for keyed tiles. README "For apps": `?app=` and `access`, `/api/apps/<key>/people`, the loop reason for `access`.
- [ ] **Step 4: Run** frontend checks and the full e2e suite — Expected: all pass.
- [ ] **Step 5: Commit** `feat: who may use which app, in Einstellungen`.
