# One look for the family apps, ready for a second theme per person

Status: worked out with the user in chat on 2026-11-28 (builder check done); waiting for their approval. Points marked "my call" are the
author's.

## Why

The user wants a second theme in the family apps later, with the look and feel of a family wall calendar (Daely
Calendar): light, friendly, soft. Before that, they want **all apps that log in through the hub to look like the hub**
(the dark "Aurora" theme), and the apps **prepared so each person can pick their theme** in the hub. Today the apps
look different from each other, and colours are written into every component (`bg-slate-800`, `text-white`, hex
codes), so a second theme would mean touching every component of every app again.

## Scope

- **Hub** (family-hub) and the six apps that log in through it: family-budget-dashboard, meal-planer, family-planner,
  family-job-tracking, fitness-tracker, family-chore.
- Not included: kids-games and brick-tidy (no hub login; the user's choice), and **Brightville** (logs in through the
  hub, but is a picture game for a kindergarten child whose look is part of the game; my call, to confirm).
- The Daely-style theme itself is **not** part of this work; it comes next, as a second set of values.

## Goals

- **One look:** every app in scope uses the hub's Aurora theme: dark slate background with the two soft radial glows,
  frosted-glass cards, cyan / magenta / indigo accents, green for success, red for danger, Inter. Apps that already
  use it (budget, meal planner, planner) keep looking as they do; job tracking, fitness and chores change to it.
- **Fully on Tailwind** (the user's choice): fitness-tracker and family-chore move from their own CSS files to
  Tailwind v4 like the others; their own CSS files are removed except a small base file (fonts, body background).
- **Colours by role, not by value:** components use role names (below) instead of palette colours, so a theme is
  only a set of values. A check in each app's `npm run lint` fails on palette colours or hex codes in components
  (my call), so it stays that way.
- **One theme package**, `family-hub-theme`, in the hub repo next to `client/`: the roles with the Aurora values, the
  glass-card and base styles, and a small helper that applies the theme to the page. A new theme is added there once
  and reaches each app with a version update.
- **Theme per person in the hub:** each person has a theme, like their language: picked in the hub's own settings,
  also from outside (like language and colour). For now the only choice is "Aurora", so the picker is shown only
  once there are two (my call).
- **The theme reaches every app:** the hub sends it with the person (`/api/session`, `/api/apps/<key>/people`),
  `family-hub-client` passes it on (`HubPerson.theme`), each app's who-am-I answer includes it, and the page sets
  `data-theme` on `<html>`.

## Non-goals

- The Daely-style theme (next step), dark/light following the operating system, a theme per device.
- Redesigning layouts, spacing or components beyond what moving to roles and Tailwind needs.
- Themes in kids-games, brick-tidy, Brightville.

## Anti-goals

- An app that looks broken or unstyled while the hub restarts or is unreachable: the theme's CSS is part of each
  app's build, never loaded from the hub at runtime.
- An app that breaks when the hub knows a theme the app doesn't have yet: unknown themes show Aurora.
- A flash of the wrong theme on every page load for a person who picked another theme.
- Visible regressions in the apps that already look right (budget, meal planner, planner).

## Approaches

- **A. A shared theme package in the hub repo** (chosen): `theme/` next to `client/`, installed by each app at an
  exact version. A new theme is built once. Cost: one more dependency per app.
- B. A copy of the theme file in every app: no dependency, but the second theme would have to be copied into seven
  places that drift apart.
- C. The hub serves the theme CSS at runtime: apps would look broken while the hub restarts, and cross-origin
  cookies and security headers get in the way from outside. Rejected.

## How it works (decided)

### Roles

Tailwind v4 `@theme` variables, so each becomes a utility (`bg-surface`, `text-muted`, `border-line`, ...):

| Role | Use | Aurora value |
|------|-----|--------------|
| `page` | page background | `#0f172a` (+ the two radial glows) |
| `surface` | cards, panels (glass) | `rgba(30, 41, 59, 0.4)` |
| `surface-strong` | dialogs, menus | `rgba(15, 23, 42, 0.6)` |
| `field` | inputs, selects | `rgba(30, 41, 59, 0.5)` (today `bg-slate-800/50`) |
| `line` | borders | `rgba(255, 255, 255, 0.1)`; inputs `#64748b` as `line-strong` |
| `ink` | main text | `#f8fafc` |
| `muted` | secondary text | `#94a3b8` |
| `accent` | links, focus, highlights | `#22d3ee` |
| `button-from`, `button-to` | the primary button's gradient (`.btn-primary`, in the package) | `#4f46e5` → `#a21caf`, as today: white text 6.3:1 |
| `accent-2`, `accent-3` | magenta, indigo highlights and charts | `#e879f9`, `#818cf8` |
| `success`, `danger`, `warning` | states | `#34d399`, `#f87171`, `#fbbf24` |
| `on-accent` | text on accent buttons | `#ffffff` |

**Fewer shades** (the user's choice, 2026-11-28): small shifts against today's look are fine, and the variation is
reduced on purpose. Today's many shades (budget: ~80 palette classes, four greys for text alone) fold into the roles
above: one main and one secondary text colour, one field style, one border (plus `line-strong`), one tint each for
success / danger / warning. No `-soft`/`-strong` variants beyond the ones in the table unless a screen can't be
read without one. Each app's pull request shows before/after screenshots of its main screens for the user to look
over; no automatic pixel comparison.

**More than colours** (the user's choice): a theme also sets

| Role | Use | Aurora value |
|------|-----|--------------|
| `--radius-card`, `--radius-control` | cards / buttons, inputs | `12px` / `8px` |
| `--shadow-card` | cards | `0 8px 32px 0 rgba(31, 38, 135, 0.37)` |
| `--blur-glass` | glass cards and dialogs | `12px` |
| `--font-sans` | all text | `'Inter', system-ui, ...` |
| `--page-glow` | the page's background image | the two radial glows |
| `hover`, `pressed` (colours) | hover / active overlays on rows, list items, ghost buttons | `rgba(255, 255, 255, 0.05)` / `0.1` |

so overlays like `hover:bg-white/5` or `bg-red-900/30`, which only work on a dark page, become roles too. The exact
list is refined when the hub is moved (the builder's call); the names are fixed once the first app depends on them.
Person colours (from the hub) and chart series colours stay as data, not roles.

### The package

- `theme/` in family-hub: `theme.css` (`@theme` with the roles, `[data-theme="aurora"]` with the values, base styles,
  `.glass-card`), `index.js` + `.d.ts` with `applyTheme(name: string | null | undefined): void` (sets
  `data-theme`, falls back to `aurora` for unknown names, remembers it in `localStorage` under `family-theme`) and
  `THEMES`. No runtime dependencies.
- A small same-origin script (`theme-init.js` from the package, copied into each app's `public/` at build time and
  loaded first in `index.html`) sets `data-theme` from `localStorage` before the page renders, so a person's theme
  shows without a flash. Not inline: the apps' security headers (`script-src 'self'`) block inline scripts (my call,
  after the review).
- **Install:** npm can't install a sub-folder of a GitHub archive, so the hub's CI packs `theme/` (`npm pack`) and
  attaches the `.tgz` to a GitHub Release tagged `theme-v<version>`; apps depend on that release asset's URL in
  `package.json` (immutable, public, no registry; my call).
- Each app: `@import "tailwindcss"; @import "family-hub-theme/theme.css";` in its CSS entry.

### Theme per person

- Hub: `Person.theme` (`String(20)`, nullable; `None` = the default, `aurora`), a migration, `PersonOut.theme`,
  `AppPerson.theme`, `PATCH /api/me` accepts `theme` (one of the hub's known themes, else 422), the same rules as
  `language` (also from outside).
- `family-hub-client`: `HubPerson.theme: str` (default `"aurora"` when the hub doesn't send it, so a new client works
  with an older hub); `FakeHub` sends it.
- Each app: its who-am-I answer gains `theme`; the frontend calls `applyTheme(me.theme)` when it loads who is logged
  in, and `applyTheme(null)` on logout / no login.

### Moving an app

Per app, one pull request: install the package, replace palette colours in components with roles, remove the app's
own copy of the Aurora variables, add the lint check, return and apply `theme`, bump `family-hub-client`. For
fitness-tracker and family-chore also: add Tailwind v4 (`@tailwindcss/vite` or PostCSS as the others), rewrite each
component's styling as Tailwind classes, delete the CSS files. The existing Playwright tests must pass, plus one new
test per app that the page has `data-theme="aurora"` after login. fitness-tracker has no Playwright tests yet: its
pull request adds a small setup (fake hub login as in the other apps, CI job) with a test per screen, since its whole
styling is rewritten (my call).

### Order (my call)

1. family-hub: package, release, `Person.theme`, client, the hub's own frontend on roles.
2. family-budget-dashboard, 3. meal-planer, 4. family-planner (already Aurora: mostly replacing colours).
5. family-job-tracking (Tailwind, own colours). 6. fitness-tracker (3 components, ~590 lines of CSS).
7. family-chore (46 components, ~2400 lines of CSS).

## Constraints

- Same stack everywhere: React 19, Vite 8, Tailwind v4, TypeScript; Docker on the NAS; images build without git.
- The repositories are public: no names, addresses or domains in the theme or tests (placeholders as today).
- German and English for any new text (the theme picker later).
- Each app stays deployable on its own: an app moved to the package must not need the others moved.

## Left to the builder

- The final list and values of the roles, refined while moving the hub; how the lint check is written (a script like
  `check-texts.mjs`, or an ESLint rule).
- Per app: the who-am-I endpoint that carries `theme` (they differ), and how the Tailwind rewrite of fitness and
  chores is split into commits.
- The release workflow details for the theme package.
