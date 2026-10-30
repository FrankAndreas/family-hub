# Hub hardening: manage cookie, own PINs only, PIN reset by e-mail, real logout

Date: 2026-10-30. Issues: family-hub#4, family-hub#6. Agreed with the user in chat on 2026-10-30; points marked
**(my call)** were settled by Claude and are open to change.

## Why

- **#4, app cookies:** every app at home gets the `hub_session` cookie. An app that leaks or logs it hands out a
  parent's full hub rights, including managing the family's people and PINs.
- **#4, parents:** any parent can set another parent's PIN, make them a child or deactivate them. The family includes
  separated parents with a common budget, so one parent must not be able to take over the other's account.
- **#6, logout:** "Log out" only removes the cookie in this browser. A copied token stays valid for up to 30 days.
- **#6, smaller items:** "at home" means "no `Cf-Connecting-Ip`", so a port forward would count as at home. Two
  parents changing each other at the same moment can leave the family without a parent.

## Goals

1. Managing the hub needs a second cookie that only the hub gets.
2. A parent changes only their own PIN, role and details; parents still manage children.
3. A forgotten PIN is reset with a link sent to the person's registered e-mail; a command on the NAS is the last
   resort.
4. "Log out" ends this login for real, in the hub and in every app; the apps log out through the hub.
5. Docs warn against port forwards; the last-parent check can't be raced.

## Non-goals

- Real per-app tokens (an OAuth-like exchange per app): the user chose the manage cookie instead. A leaked
  `hub_session` still logs into the other apps at home; it no longer manages the hub.
- Incoming mail or the Cloudflare Email Worker: the hub only sends, straight to Resend (as family-job-tracking does).
- Resetting a PIN from outside: PIN login and managing stay home-only (decided 2026-10-29).

## Anti-goals

- Nothing may tell a stranger whether a name or e-mail address exists, or whether a mail was sent.
- No token, reset link, cookie or e-mail address in any log line.
- A parent must never end up with no way back in: e-mail reset, and the NAS command when that fails.

## 1. Manage cookie

- A PIN login at home sets two cookies:
  - `hub_session`, as today (domain `COOKIE_DOMAIN`, lax, 30 days);
  - new: `hub_manage`, host-only (no domain), HttpOnly, Secure unless `COOKIE_INSECURE=1`, `SameSite=strict`,
    path `/api`, same lifetime.
- Both are EdDSA JWTs from the same key, told apart by a claim:
  - session tokens get `typ: "session"` and an id `jti`;
  - manage tokens get `typ: "manage"` and `sid`, the `jti` of the session token issued with them.
- A token of the wrong type is no login anywhere (a manage token sent as Bearer to `/api/session` is invalid).
- **Needs both cookies, same person, `sid` = the session's `jti`:** every request that changes something in the hub:
  - people: add, change, set a PIN;
  - `PUT /me/pin`, `PATCH /me`;
  - tiles: add, change, delete, order;
  - `GET /people` and `GET /tiles/manage` **(my call:** they list e-mail addresses and access lists).
- **Needs only `hub_session`:** reading (`/api/me`, `/api/tiles`, `/api/people/public`), the apps' calls
  (`/api/session`, `/api/apps/<key>/people`), `/api/logout` and `/api/logout-everywhere`.
- From outside (through the tunnel) there are no cookies, only the Cloudflare login. `PATCH /me` (language and colour)
  keeps working there with that login, as today **(my call)**; everything else that manages stays home-only.
- Without a valid manage cookie, a managing request gets 403 with code `login_again`. The hub's pages show "Log in
  again to change this" and a button to the login.
- `PUT /me/pin` sets new cookies for this device, as it does now, both of them.

## 2. Own PIN only; parents manage children

- **A parent may:**
  - add people, children or parents (new people need a PIN, as today);
  - change a child: name, e-mail, role (also to parent), active, colour, language, PIN;
  - change themselves through `PATCH /people/{own id}`: name, e-mail, colour, language, role, active. Making
    themselves a child or inactive keeps the last-parent check.
- **A parent may not:** change another parent in any way, or set another parent's PIN. That's 403 `other_parent`.
- **Own PIN:** only through `PUT /me/pin` with the old PIN (as today), or the e-mail reset.
- **Own e-mail address:** changing it needs the current PIN in the request **(my call:** the address is the
  recovery channel, so a forgotten browser at home must not be enough to redirect it). Wrong PINs count toward the
  lock, like `PUT /me/pin`.
- **Settings page:** another parent's row shows name and role, without edit controls.
- **Last-parent check:** it runs under one process-wide lock (like the PIN lock), re-reading the parents inside the
  lock, so two requests can't both pass it.

## 3. Forgot PIN: reset link by e-mail

- **Settings:**
  - `RESEND_API_KEY`, `MAIL_FROM` (as in family-job-tracking);
  - `HUB_PUBLIC_URL` (e.g. `https://home.local.<domain>`), for the link.
  - Without all three, the reset by mail is off: `/api/config` reports `pin_reset: false` and the login screen shows
    no "Forgot PIN?".
- **Request:**
  - Flow: login screen → "Forgot PIN?" → pick the name (the login screen's list) → `POST /api/pin-reset {name}`.
  - At home only, with the app header, no login needed.
  - The answer is always 200 with the same text, "If an e-mail address is registered, a link is on its way." That
    holds for unknown names, people without e-mail, inactive people, the limit reached, and mail errors.
  - Anyone with an e-mail address can use it, children too.
- **Limit:** at most 3 reset mails per person per hour; requests beyond that are silently dropped.
- **Link:**
  - `<HUB_PUBLIC_URL>/reset-pin?token=<random 32 bytes, urlsafe>`;
  - the hub stores only its SHA-256, with person, created time, expiry (30 minutes) and used time;
  - one use; using one ends that person's other open reset links.
- **Mail:** plain text plus simple HTML, in the person's language (default language otherwise). Subject "Familien-Hub:
  neue PIN" / "Family hub: new PIN". It says the link works at home only, for 30 minutes, and that the mail can be
  ignored if nobody asked for it. It's sent through the Resend API with a 20 s timeout; a failure is logged as
  "PIN reset mail failed: <error kind>", without address or link.
- **Reset page `/reset-pin`:**
  - new PIN twice → `POST /api/pin-reset/confirm {token, pin}`;
  - on success, the new PIN takes effect the same way as setting a PIN today: all logins end and the lock is
    lifted. The page then says "PIN changed" and goes to the login **(my call:** no automatic login).
  - An unknown, used or expired link gives 400 `reset_link_invalid`, with "This link has expired. Ask for a new one."
  - At home only.
- **NAS command (last resort):**
  - `docker exec hub-backend python -m app.reset_pin <name>` prints a reset link (same table, 30 minutes) to the
    terminal.
  - It works without the mail settings and for people without an address.
  - Unknown or inactive names exit with an error.
  - README_DOCKER documents it, and also the case where `HUB_PUBLIC_URL` is unset: then it prints the path to open on
    the hub's address.

## 4. Logout ends this login; apps log out through the hub

- Session tokens carry `jti`.
- `POST /api/logout`:
  - records the `jti` of the session cookie it gets in a new `ended_logins` table (jti, expires_at = token expiry);
  - clears both cookies;
  - also drops expired rows from `ended_logins`.
- A token whose `jti` is in `ended_logins` is no login (`person_for_token` and the manage check). Apps notice through
  `/api/session` within their cache time (60 s in the budget app).
- "Log out everywhere" is unchanged (raises `token_version`).
- `/logout` is a page, so any site could link someone there and log them out. That's accepted as a nuisance: it
  ends a login, it never starts one.
- **Old tokens:** they have no `typ`/`jti`. The migration raises every person's `token_version`, so everyone logs in
  once more after the update.
- **Hub frontend:** a route `/logout` that calls `POST /api/logout` and then shows the login. Its `?next=` (checked
  with `safeNext` against the tiles, as at login) is kept for after the next login.
- **Budget app** (`FrankAndreas/family-budget-dashboard`):
  - "Log out" sends the browser to `<HUB_PUBLIC_URL>/logout?next=<the app's address>`;
  - the budget backend's own `POST /logout` is no longer used by the frontend **(my call:** remove it, including its
    tests and #133, which then no longer applies).
  - Apps switched later do the same; the hub README's "For apps" section says so.
- **Merge order:** the hub PR first, deployed; then the budget PR. A budget logout pointing at an old hub without
  `/logout` would show the hub's start page instead.

## 5. Docs

README_DOCKER gets a "Reaching the hub from outside" warning: only through the Cloudflare tunnel, never a router port
forward to the NAS or the DSM reverse proxy. Such requests carry no `Cf-Connecting-Ip` and would count as at home.

## Data changes (migration 0004)

- `pin_resets`: id, person_id (FK people, cascade), token_hash (unique), created_at, expires_at, used_at.
- `ended_logins`: jti (primary key), expires_at.
- Data step: `people.token_version += 1` for everyone.

## Tests the builder must include

- Manage cookie:
  - a request with `hub_session` alone can't manage (403 `login_again`), but can read;
  - a manage token is no session token, nor the other way round;
  - a manage cookie from another login (wrong `sid`) is refused;
  - the cookie flags are as above.
- Parents:
  - can't change another parent, or set their PIN (403 `other_parent`);
  - can change children and themselves;
  - changing their own e-mail needs the right PIN;
  - the last-parent check holds under parallel requests.
- Reset:
  - the same answer for unknown, no-mail, inactive, limited and failing cases;
  - limit of 3 per hour;
  - link expiry, single use, other links ended;
  - a new PIN ends logins and lifts the lock;
  - not through the tunnel;
  - nothing in logs (capture the log and check that no token, link or address appears);
  - off without settings;
  - the NAS command prints a working link.
- Logout:
  - an ended token is invalid at `/api/session`, while another device's token still works;
  - expired rows are cleaned up;
  - old tokens without `jti` are invalid after the migration.
- Browser tests:
  - forgot PIN → link (taken from a fake sender in e2e) → new PIN → login;
  - another parent's row has no edit controls;
  - `/logout?next=` ends the login and returns to the app after the next login.
- Budget app: "Log out" goes to the hub's `/logout` with `next`.

## Left to the builder

- Texts and screen layout, in the hub's existing style, with de/en texts for every new error code.
- How the e2e captures mails: a fake sender switched on by an environment variable that only tests set.
- Splitting into commits and tasks.
