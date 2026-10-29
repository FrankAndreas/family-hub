# family-hub: one start page and one family login for all family apps

Status: worked out with the user in chat on 2026-10-29; waiting for their approval. Points marked "my call" are the
author's.

## Why

The family runs several self-hosted apps on one Synology NAS (DS720+): family-budget-dashboard, family-chore,
family-job-tracking, meal-planer, fitness-tracker, kids-games, brick-tidy (my-house is a calculator not deployed yet).
Today:

- There is no common place to start: every app has its own address and port.
- The four apps with logins (budget, chore, jobs, meal planner) each keep **their own list of people** with a 4-digit
  PIN. A new family member, a changed PIN or a new e-mail address has to be entered in every app, and every app asks
  for its own PIN.

The user wants one start page with a tile per app, and one login that every app accepts. Keycloak was considered and
is too heavy for the NAS and a poor fit for PINs (my call, agreed in chat).

## How the apps are reached today

- **At home**: `<app>.local.<domain>`, DNS only to the NAS (<NAS_IP>), HTTPS by the DSM reverse proxy
  with a wildcard certificate. Cloudflare is not in the path.
- **From outside**: `<app>.<domain>` through one Cloudflare Tunnel on the NAS, behind **Cloudflare Access**
  (the family's e-mail addresses; e-mail code or Google). An app is reachable from outside only if the tunnel has a
  route for it. The budget app has none for people (only its mail worker's path), so it is home-only, as the user
  wants.

## Goals

- **Start page** `home.<domain>` (outside) and `home.local.<domain>` (at home): a tile per app (name,
  icon), opening the app in full screen. Only the apps reachable from where one is are shown (my call): at home all,
  from outside those with a tunnel route.
- **family-hub manages all people**: name, e-mail address, PIN, active or not, parent or child, a colour or picture
  (my call). Adding a family member or changing a PIN happens here only.
- **One login per device**:
  - At home: the hub's login (name + PIN) sets a login cookie valid for every app at home
    (`Domain=local.<domain>`, so browsers never send it to the outside addresses; my call).
  - From outside: Cloudflare Access is the login; apps trust its signed token (`Cf-Access-Jwt-Assertion`) and find the
    person by e-mail address. No PIN outside.
  - Switching apps never asks again. A logout in the hub or any app logs out of all apps on that device. A login lasts
    30 days (my call; jobs and meal planner use 30 days today, budget about 2).
- **Managing at home only** (the user's choice after the security review): people, PINs (also one's own) and the
  apps are managed at home only. From outside one uses the apps and changes one's language and colour; a parent's
  mailbox someone broke into gets past Cloudflare Access but can't take over the family's accounts.
- **Apps keep their own details** per person (budget: allowance child, privacy, shares; meal planner: language, ...),
  keyed by the hub's person id.
- **No breakage during the change**: the hub comes first, then one app at a time switches; an app not switched yet
  keeps its own PIN login.

## Non-goals

- Embedding apps in the hub page (iframes): tiles open the app; each app gets a small "⌂ Hub" link back.
- A "who are you?" picker or quick person switch on shared devices: manual logout / login is enough.
- Logins for the apps that have none today (fitness-tracker, kids-games, brick-tidy, my-house): they get tiles and stay
  as they are in this version.
- Keycloak, Authentik or another identity server; passwords; two-factor at home.
- Changing which apps are reachable from outside: that stays a setting of the tunnel's routes in Cloudflare.

## Anti-goals

- An app reachable from outside without Cloudflare Access in front.
- A PIN or a login cookie that works from outside on its own: at home the hub's cookie, outside only Cloudflare's token
  (the cookie is scoped to `local.<domain>`, and the hub's PIN login refuses requests that come through the
  tunnel; my call).
- Losing an app's data when it moves to the hub's people.
- A secret copied into every app.
- Real names, e-mail addresses or PINs in the public repositories.

## How it works (decided)

- **Stack** like the other apps: FastAPI + SQLite backend, React + Vite + Tailwind frontend, Docker on the NAS,
  deployed with the same nas-update / deploy-nas scripts, German by default and English per person.
- **Login token**: the hub signs it with its private key; apps check it with the hub's public key (fetched from the
  hub, e.g. a JWKS endpoint), so no shared secret (my call). It names the person (hub id) and its expiry. Logging out
  everywhere makes all earlier tokens invalid (as "log out everywhere" works in the apps today).
- **Cloudflare token**: apps verify it against the Cloudflare team's public keys and the Access application's audience,
  then ask the hub which person has that e-mail address.
- **Security moves to the hub**: wrong-PIN limits and lock-outs, the first-start Admin with a random PIN, "log out
  everywhere".
- **Moving an app over**: its existing users are matched once to hub people by name; unmatched ones are shown to a
  parent to pick by hand (my call). The app's data stays on its own user rows, which then point to the hub person.
- **Order** (my call): hub with its people and start page; then family-budget-dashboard; then the others
  (meal-planer, family-job-tracking, family-chore).

## Constraints

- Runs on the DS720+ next to the other apps: light on memory, one more container pair.
- The repositories are public: no real names, addresses, IBANs or PINs in code, tests or docs; docs use placeholders
  (`<domain>`, `<NAS_IP>`).
- The apps' existing HTTPS setup stays: wildcard certificate for `*.local.<domain>`, DSM reverse proxy.
- German and English texts.

## Left to the builder

- The hub's own API shape (people, login, logout, keys) and how apps cache the public keys and the people list.
- Whether the shared app-side code (verify hub token / Cloudflare token, map to a local user) becomes a small package
  the apps install or is copied per app.
- The start page's tile list: configured in the hub (name, icon, local and outside address, "home only"), my call.
- Exact wording, layout and icons, in the family apps' look.
