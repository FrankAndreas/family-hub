# Hub Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the following to the family hub:
- a host-only manage cookie;
- parents changing only their own PIN and details;
- PIN reset by e-mail, with a command on the NAS as the last resort;
- a logout that really ends the login.

The budget app then logs out through the hub.

**Architecture:**
- Session and manage tokens are EdDSA JWTs from the existing key, told apart by `typ`.
- Session tokens carry `jti`. Logout records it in `ended_logins`.
- The manage token's `sid` binds it to its session.
- PIN resets are hashed one-time tokens in `pin_resets`, mailed through the Resend API.
- The new tables and the logout of everyone come in migration 0004.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, PyJWT, React 19 + TS + Vite + react-i18next, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-30-hub-hardening-design.md` (family-hub). Read it; values below are copied
from it.

## Global Constraints

- **Cookies:**
  - `hub_session`: domain `COOKIE_DOMAIN`, lax, 30 days, unchanged.
  - `hub_manage`: host-only, HttpOnly, Secure unless `COOKIE_INSECURE=1`, `SameSite=strict`, path `/api`, 30 days.
- **Claims:**
  - session `typ: "session"` + `jti` (uuid4 hex);
  - manage `typ: "manage"` + `sid` (= the session's jti);
  - both keep `iss`, `sub`, `ver`, `exp`.
- **New error codes:** `login_again` (403), `other_parent` (403), `pin_needed` (400), `reset_link_invalid` (400).
  Each gets de and en texts in `frontend/src/locales/{de,en}.ts`, with the same keys.
- **Reset:**
  - link `<HUB_PUBLIC_URL>/reset-pin?token=<secrets.token_urlsafe(32)>`, valid 30 minutes, single use;
  - at most 3 mails per person per hour;
  - always the same 200 answer `{"ok": true}`;
  - at home only.
- **Mail:**
  - settings `RESEND_API_KEY`, `MAIL_FROM`, `HUB_PUBLIC_URL`; reset is off unless all three are set;
  - Resend timeout 20 s;
  - subjects "Familien-Hub: neue PIN" / "Family hub: new PIN".
- **Never in a log line:** a token, reset link, cookie or e-mail address. On failure, log only
  `PIN reset mail failed: <error kind>`.
- **Repo rules:** invented people only (the repo is public); `<domain>` and `<NAS_IP>` placeholders in docs.
- **Checks per task:**
  - `.superpowers/venv/bin/pytest -q -p no:warnings tests`;
  - `.superpowers/venv/bin/black --check backend tests`;
  - `.superpowers/venv/bin/flake8 --max-line-length=120 --extend-ignore=E203,W503 backend tests`;
  - `cd backend && ../.superpowers/venv/bin/mypy app`;
  - when the frontend changes, `cd frontend && npm run lint && npm run type-check && npm run build && npm test`;
  - e2e: `cd e2e && E2E_PYTHON=../.superpowers/venv/bin/python npm test`.
- **Commits** end with the session's `Co-Authored-By` and `Claude-Session` lines.

## Review Focus

1. **A browser still logged in from before the update** (old token: no `typ`, no `jti`): it must land on the login
   screen with no error loop. `/api/me` gives 401. Test in Task 1.
2. **A name typed in another case in "Forgot PIN"** (`admin` for `Admin`): it must reach the same person as the login
   does. Test in Task 4.
3. **Changing your own PIN in Settings**: this device must keep managing afterwards (new `hub_manage` with the new
   `sid`). Test in Task 2.
4. **An opened reset link after the person changed their PIN another way**: it still works once and ends the logins.
   Covered by the single-use test, nothing extra.
5. **A parent's settings page with another parent listed**: that row has no edit button, and their own row still has
   one. E2E in Task 6.

---

### Task 1: Session tokens with typ/jti, ended logins, migration 0004

**Files:**
- Create: `backend/app/migrations/versions/0004_hardening.py`
- Modify: `backend/app/models.py`, `backend/app/auth.py`, `backend/app/people_api.py`, `backend/app/database_setup.py`
  (`HEAD = "0004"`)
- Test: `tests/test_hardening_logout.py`

**Interfaces:**
- Produces:
  - `models.EndedLogin(jti: str PK String(32), expires_at: datetime)`;
  - `models.PinReset(id, person_id FK cascade, token_hash String(64) unique, created_at, expires_at,
    used_at: datetime | None)`;
  - `auth.issue_tokens(person) -> tuple[str, str]` (session, manage);
  - `auth.token_claims(token: str | None, typ: str) -> dict | None` (decoded, right `typ`, not expired);
  - `auth.person_for_token(db, token)`, which now also needs `typ == "session"` and a `jti` not in `ended_logins`;
  - `auth.set_cookies(response, session: str, manage: str)` and `auth.clear_cookies(response)` (both cookies);
  - `auth.end_login(db, token: str | None) -> None`, which records the jti and deletes expired rows;
  - `auth.MANAGE_COOKIE = "hub_manage"`.
  `issue_token`, `set_cookie` and `clear_cookie` go away; update every caller (`login`, `logout`,
  `logout-everywhere`, `PUT /me/pin`).
- The migration creates both tables, with named constraints (`pk_…`, `uq_pin_resets_token_hash`,
  `fk_…_person_id_people`), and runs `UPDATE people SET token_version = token_version + 1`.

- [ ] **Step 1: Write failing tests** in `tests/test_hardening_logout.py`:
  - `test_logout_ends_this_login_only`:
    - login on client A and on client B; save A's `hub_session`; A `POST /api/logout`;
    - `GET /api/session` with `Authorization: Bearer <A's saved token>` → `valid is False`;
    - B's `/api/me` → 200.
  - `test_logout_clears_both_cookies`: the `set-cookie` headers of `/api/logout` include `hub_session=""` and
    `hub_manage=""`.
  - `test_ended_logins_are_cleaned_up`: insert an `EndedLogin` with `expires_at` in the past, log out once, and that
    row is gone.
  - `test_manage_token_is_no_session`: Bearer with the `hub_manage` cookie's value to `/api/session` →
    `valid is False`.
  - `test_old_token_without_jti_is_invalid` (Review Focus 1): sign `{"iss","sub","ver","exp"}` with
    `keys.signing_key()` (EdDSA, kid header), set it as `hub_session`, and `/api/me` → 401.
  - `test_migration_logs_everyone_out`: in a tmp db, upgrade to 0003, insert a person with `token_version` 0, upgrade
    to head, and the person has `token_version == 1`. Use `database_setup.run(engine, command.upgrade, "0003")`.
- [ ] **Step 2:** Run `pytest tests/test_hardening_logout.py -q`. Expected: all FAIL (no `hub_manage` cookie,
  `EndedLogin` missing).
- [ ] **Step 3:** Implement the models, the migration and the auth functions above, and switch `login`, `logout`,
  `logout-everywhere` and `PUT /me/pin` to `issue_tokens`/`set_cookies`/`clear_cookies`. `logout` calls
  `end_login(db, request.cookies.get(COOKIE))`.
- [ ] **Step 4:** Run the whole backend suite plus black, flake8 and mypy. Expected: all pass. Fix existing tests that
  read only `hub_session` where needed.
- [ ] **Step 5:** Commit `feat(auth): logins end for real at logout; session and manage tokens (#6)`.

### Task 2: Managing needs the manage cookie

**Files:**
- Modify: `backend/app/auth.py`, `backend/app/people_api.py`, `backend/app/tiles_api.py`
- Test: `tests/test_hardening_manage.py`

**Interfaces:**
- Consumes: Task 1's `token_claims`, `MANAGE_COOKIE`, `person_for_token`.
- Produces: `auth.require_manager(request, person=Depends(current_person), db=Depends(get_db)) -> models.Person`.
  - It is home only: through the tunnel → 403 `manage_at_home_only`, as today.
  - The `hub_manage` claims must have `typ` manage, `sub == person.id`, `ver == person.token_version`, and `sid` equal
    to the `jti` of the request's `hub_session`. The `sid` must not be ended. Anything else → 403 `login_again`.
- `require_parent` now builds on `require_manager`.
- **Endpoints that need `require_manager`:**
  - `PUT /me/pin`;
  - `PATCH /me`, except through the tunnel, where the Cloudflare login is enough (spec §1);
  - every `require_parent` endpoint: `/people` GET/POST/PATCH, `/people/{id}/pin`, `/tiles/manage`, and tiles
    POST/PATCH/DELETE/order.
- **Endpoints left as they are:** `/api/me` GET, `/api/tiles` GET, `/people/public`, `/logout`,
  `/logout-everywhere`, `/api/session`, `/api/apps/...`.

- [ ] **Step 1: Write failing tests:**
  - `test_session_cookie_alone_cant_manage`:
    - log in, then delete `hub_manage` from `client.cookies`;
    - `GET /api/people` → 403, `detail == "login_again"`;
    - `PATCH /api/me {"color": "#112233"}` → 403;
    - `GET /api/me` → 200; `GET /api/tiles` → 200.
  - `test_manage_cookie_of_another_login_is_refused`:
    - log in on client A and client B;
    - put A's `hub_session` together with B's `hub_manage` on a third client;
    - `GET /api/people` → 403 `login_again`.
  - `test_manage_cookie_flags`: the login's `hub_manage` set-cookie has no `Domain=` (even with
    `COOKIE_DOMAIN=local.example.ch`), and has `HttpOnly`, `SameSite=strict`, `Path=/api`.
  - `test_own_pin_change_keeps_managing` (Review Focus 3): log in, `PUT /api/me/pin` with the old and a new PIN, then
    `GET /api/people` on the same client → 200.
  - `test_outside_can_still_change_own_colour`: with the Cloudflare setup from `test_cloudflare`
    (`access`/`outside` fixtures), `PATCH /api/me` through the tunnel → 200.
- [ ] **Step 2:** Run them. Expected: FAIL. `test_manage_cookie_flags` and `test_own_pin_change_keeps_managing` may
  already pass after Task 1; keep them as guards.
- [ ] **Step 3:** Implement `require_manager` and wire the endpoints as listed.
- [ ] **Step 4:** Run the whole suite and the linters. Expected: pass.
- [ ] **Step 5:** Commit `feat(auth): managing the hub needs a cookie only the hub gets (#4)`.

### Task 3: Parents change only themselves; own e-mail needs the PIN; last-parent lock

**Files:**
- Modify: `backend/app/people_api.py`, `backend/app/schemas.py` (`PersonPatch.current_pin: str | None`, pattern PIN)
- Test: `tests/test_hardening_parents.py`

**Interfaces:**
- Consumes: Task 2's `require_parent` (now returns the acting parent; use it as a parameter, not only in
  `dependencies=`).
- **Rules in `change_person` and `set_pin`:**
  - If the target is a PARENT and not the actor → 403 `other_parent`. That applies to every field, and to setting the
    PIN.
  - Own e-mail: if `"email" in fields`, the target is the actor and the value changes, then `current_pin` must be
    given, else 400 `pin_needed`. It is checked with `auth.check_pin(db, actor, current_pin, api_error(401,
    "wrong_pin"))`.
- **The last-parent check:** it and the commit run under a module-level `threading.Lock` (`_parents_lock`), and the
  others are re-queried inside the lock.

- [ ] **Step 1: Write failing tests:**
  - `test_parent_cant_change_another_parent`:
    - Admin adds parent "Mia" (PIN 5678);
    - `PATCH /api/people/{mia} {"color": "#000000"}` → 403 `other_parent`;
    - `PUT /api/people/{mia}/pin {"pin": "9999"}` → 403;
    - `PATCH {"active": false}` → 403.
  - `test_parent_still_manages_children`: add child "Lena"; PATCH name and PIN → 200.
  - `test_parent_changes_themselves`: Admin `PATCH /api/people/{own} {"color": "#123456"}` → 200.
  - `test_own_email_needs_pin`:
    - `PATCH own {"email": "admin@example.org"}` → 400 `pin_needed`;
    - with `current_pin: "0000"` → 401 `wrong_pin`;
    - with `current_pin: "1234"` → 200;
    - a child's e-mail changes without a PIN → 200.
  - `test_last_parent_check_holds_in_parallel`:
    - Admin and Mia are parents, each logged in on their own client;
    - in two threads at once, each makes themselves a child (`PATCH own {"role": "CHILD"}`);
    - slow `auth.name_key` or the query with monkeypatch if needed to widen the window;
    - exactly one gets 200 and the other gets 400 `last_parent`.
- [ ] **Step 2:** Run them. Expected: FAIL (403s missing, no `pin_needed`).
- [ ] **Step 3:** Implement the rules above.
- [ ] **Step 4:** Run the whole suite and the linters. Expected: pass. Existing tests where Admin changes another
  parent must change to a child or to Admin themselves; don't weaken what they check.
- [ ] **Step 5:** Commit `feat(people): parents change only themselves and children; own e-mail needs the PIN (#4, #6)`.

### Task 4: PIN reset by e-mail, and the NAS command

**Files:**
- Create: `backend/app/pin_reset.py`, `backend/app/reset_pin.py` (the command), `tests/test_pin_reset.py`
- Modify: `backend/app/people_api.py` (routes; `/config` adds `"pin_reset": pin_reset.is_configured()`),
  `backend/app/config.py` if helpful

**Interfaces:**
- Consumes: Task 1's `models.PinReset`; `people_api._new_pin` (move it to `pin_reset` or `auth` if that avoids a
  cycle).
- **Produces in `pin_reset.py`:**
  - `RESEND_URL = "https://api.resend.com/emails"`, `LINK_LIFETIME = timedelta(minutes=30)`, `MAX_PER_HOUR = 3`;
  - `Sender = Callable[[str, list[str], str, str, str], None]` (mail_from, to, subject, text, html);
  - `resend_send(mail_from, to, subject, text, html) -> None`, the same shape as family-job-tracking's
    `reminders.resend_send`;
  - `is_configured() -> bool`;
  - `create_link(db, person) -> str` (stores the hash, returns the full link, or the path when `HUB_PUBLIC_URL` is
    empty);
  - `request_reset(db, name: str, send: Sender | None = None) -> None` (never raises for unknown, no-mail, inactive,
    limited or mail errors; looks people up by `auth.name_key`);
  - `confirm(db, token: str, pin: str) -> None` (raises `api_error(400, "reset_link_invalid")`; on success
    `_new_pin`, marks it used, ends the person's other open links).
  - If `MAIL_OUTBOX` is set, mails are appended as JSON lines `{"to", "subject", "text"}` to that file instead of being
    sent. Only the e2e sets it, and a comment says so.
- **Routes** (both `dependencies=[Depends(auth.require_home)]`): `POST /api/pin-reset` with body `{name}` → always
  `{"ok": true}`; `POST /api/pin-reset/confirm` with body `{token, pin}` (pin pattern PIN) → `{"ok": true}`.
- **`python -m app.reset_pin <name>`:** prints the link and returns 0; an unknown or inactive name prints an error to
  stderr and returns 1. It uses `database.SessionLocal`.

- [ ] **Step 1: Write failing tests** (a fake `send` collects calls; set env `RESEND_API_KEY=test`,
  `MAIL_FROM=hub@example.org`, `HUB_PUBLIC_URL=https://home.local.example.ch` with monkeypatch):
  - `test_same_answer_for_everyone`:
    - covers an unknown name, a person without e-mail, an inactive person, and a failing sender (raises `OSError`);
    - each is 200 with the same body;
    - only the person with an e-mail gets a call to `send`.
  - `test_name_in_another_case` (Review Focus 2): `request_reset(db, "admin", send)` with Admin's e-mail set → one
    mail.
  - `test_three_per_hour`: 4 requests → 3 mails.
  - `test_link_works_once_and_ends_others`:
    - two links; confirm the second with a new PIN → 200;
    - the second again → 400 `reset_link_invalid`; the first → 400;
    - the old login is ended (`/api/me` 401); the new PIN logs in.
  - `test_link_expires`: move the stored `expires_at` to the past → 400.
  - `test_reset_lifts_the_lock`: lock Admin with 5 wrong PINs, reset, and the new PIN logs in.
  - `test_not_through_the_tunnel`: both routes with `THROUGH_TUNNEL` → 403.
  - `test_off_without_settings`: without the env, `/api/config` has `pin_reset: false`, and `request_reset` sends
    nothing.
  - `test_nothing_secret_in_logs` (`caplog` at DEBUG): request with a failing sender, then confirm. No log record
    contains the token, the link or the address.
  - `test_mail_in_person_language`: a person with `language="en"` gets the subject `"Family hub: new PIN"`; a default
    (de) person gets `"Familien-Hub: neue PIN"`.
  - `test_nas_command_prints_a_working_link`: `reset_pin.main(["Admin"])` → 0, and the printed token (parsed from
    stdout) confirms a new PIN; `main(["Nobody"])` → 1.
- [ ] **Step 2:** Run them. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement as above.
- [ ] **Step 4:** Run the whole suite and the linters. Expected: pass.
- [ ] **Step 5:** Commit `feat(pin): reset a forgotten PIN by e-mail; NAS command as the last resort (#4)`.

### Task 5: Hub frontend

**Files:**
- Modify:
  - `frontend/src/App.tsx` (routes `/logout` and `/reset-pin` work logged in or not);
  - `frontend/src/AuthContext.tsx`;
  - `frontend/src/pages/Login.tsx` ("Forgot PIN?" when `/api/config` has `pin_reset`);
  - `frontend/src/components/PeopleSettings.tsx`;
  - `frontend/src/pages/Settings.tsx` (if the own e-mail is edited there);
  - `frontend/src/api.ts`;
  - `frontend/src/locales/{de,en}.ts`;
  - `frontend/src/types.ts`.
- Create: `frontend/src/pages/Logout.tsx`, `frontend/src/pages/ResetPin.tsx`, `frontend/src/pages/ForgotPin.tsx` (or
  a mode of Login)

**Interfaces:**
- Consumes: the routes and error codes from Tasks 1–4.
- **`/logout?next=`:** POST `/api/logout`, then clear the person, then go to `/?next=<next>`. `next` is kept only if
  `safeNext` would accept it after login (Login already checks it).
- **`login_again` (403) on any request:** show the error text with a button that logs out and goes to the login. This
  can live in `errorMessage` plus a small banner component.
- **PeopleSettings:**
  - another parent's row shows name and role with no edit button;
  - when editing one's own row, the e-mail field shows a "current PIN" input once the address changed, and sends it
    as `current_pin`.
- **Forgot PIN:**
  - pick a name (same list as login) → POST → always the text "If an e-mail address is registered, a link is on its
    way.";
  - `/reset-pin?token=` takes a new PIN twice → confirm → "PIN changed" → login.

- [ ] **Step 1: Write failing unit tests** where logic is pure, e.g. a helper `logoutTarget(next: string | null): string`
  in `next.ts` → `'/?next=' + encodeURIComponent(next)` or `'/'`; tests in `next.test.ts`.
- [ ] **Step 2:** Run `npm test`. Expected: FAIL.
- [ ] **Step 3:** Implement the pages and texts. Every new error code from the Global Constraints gets de/en texts, and
  `npm run lint` runs `check-texts.mjs`.
- [ ] **Step 4:** Run lint, type-check, build and test. Expected: pass.
- [ ] **Step 5:** Commit `feat(ui): logout page, forgot PIN, reset page; other parents read-only`.

### Task 6: E2E and docs

**Files:**
- Modify:
  - `e2e/playwright.config.ts` (backend env: `RESEND_API_KEY: 'test'`, `MAIL_FROM: 'hub@example.org'`,
    `HUB_PUBLIC_URL: 'http://localhost:3110'`, `MAIL_OUTBOX: <tmp file>`);
  - `e2e/tests/hub.spec.ts`, `e2e/tests/helpers.ts` (read the outbox);
  - `README.md` ("For apps": log out via `<hub>/logout?next=`; managing needs the hub's own cookie; PIN reset);
  - `README_DOCKER.md` (Resend settings, the NAS command, "Reaching the hub from outside": never a port forward);
  - `docker-compose.yml` and `.env.example` (`RESEND_API_KEY`, `MAIL_FROM`, `HUB_PUBLIC_URL`; never `MAIL_OUTBOX`).

- [ ] **Step 1: Write e2e tests:**
  - `forgot PIN by e-mail`: give Admin an e-mail in Settings (with the PIN), log out, Forgot PIN, read the link from the
    outbox, set PIN 2222, and log in with 2222.
  - `other parents are read-only` (Review Focus 5): add parent "Mia"; Mia's row has no edit button, and Admin's own
    row does.
  - `logout with next`: `/logout?next=<a tile's URL>` shows the login; after the login the browser goes to that URL
    (create a tile pointing at a local address first).
- [ ] **Step 2:** Run e2e. Expected: the new tests fail until Task 5 is in. They are run after Task 5, so they should
  pass; if one fails, debug it.
- [ ] **Step 3:** Write the docs as listed.
- [ ] **Step 4:** Run e2e and all checks. Expected: pass.
- [ ] **Step 5:** Commit `test(e2e): reset by mail, read-only parents, logout; docs`.

### Task 7: Budget app logs out through the hub (repo family-budget-dashboard, own branch, PR after the hub deploy)

**Files:**
- Modify:
  - `frontend/src/AuthContext.tsx` (logout), `frontend/src/api.ts` (`goToHubLogout()` next to `goToHub`);
  - `backend/app/api.py` (remove `POST /logout`);
  - tests that use it: `tests/test_hub_login.py::test_logout_clears_cookie`,
    `tests/test_hub_review_fixes.py::test_logout_needs_the_header`/`test_logout_forgets_only_this_login`;
  - the e2e that clicks "Log out" (check with `grep -rn logout e2e/tests`).
  - The `COOKIE_DOMAIN` setting stays in compose and docs only if something still uses it; otherwise remove it from
    `docker-compose.yml`, `.env.example` and the READMEs.

**Interfaces:**
- `goToHubLogout(): Promise<void>` gets `login_url` from `GET /api/v1/hub` (as `goToHub` does) and sets
  `window.location.href = login_url + '/logout?next=' + encodeURIComponent(window.location.origin)`.

- [ ] **Step 1:** An e2e test `log out goes through the hub`: click Log out; expect the URL `^<HUB>/logout\?next=` or
  the hub's login. The e2e hub runs only a backend, so assert the URL as `hub-login.spec.ts` does.
- [ ] **Step 2:** Run it. Expected: FAIL (it stays in the app).
- [ ] **Step 3:** Implement; remove the backend endpoint and its tests, and close #133 in the PR text.
- [ ] **Step 4:** Run the budget checks: pytest, black, flake8 app, mypy, frontend lint/type-check/build, e2e (34+).
  Expected: pass.
- [ ] **Step 5:** Commit `feat(auth): log out through the family hub`. Push and open a PR only after the hub PR is
  merged and deployed.
