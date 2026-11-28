# Themes, step 1: the hub – Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The hub stores a theme per person and sends it to the apps, ships the `family-hub-theme` package (roles
with the Aurora values), and its own frontend uses only roles.

**Architecture:** `Person.theme` (nullable, default `aurora`) flows through `PersonOut` / `AppPerson` and
`family-hub-client`'s `HubPerson.theme`. `theme/` is a dependency-free npm package (CSS roles as Tailwind v4 `@theme`
variables, `applyTheme`, `theme-init.js`). The hub frontend uses it via `file:../theme`, so its image is built from
the repo root. A tag `theme-v<version>` publishes the packed `.tgz` as a GitHub Release asset for the apps.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest; React 19, Vite 8, Tailwind v4, vitest, Playwright; GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-28-themes-design.md`

## Global Constraints

- Themes known now: `aurora` only. `None` in the database = `aurora`. Unknown theme names show Aurora (frontend);
  the hub's API refuses unknown names with 422.
- `theme` is the person's own choice, like `language`: `PATCH /api/me`, also from outside. Not in `PersonPatch`.
- The theme CSS is part of every build, never loaded from the hub at runtime.
- No inline scripts (CSP `default-src 'self'`): `theme-init.js` is a same-origin file.
- Small shade shifts against today's hub look are fine; fewer shades on purpose (spec "Fewer shades"). Before/after
  screenshots of Login, Start and Settings go into the PR description.
- No palette colour classes (`slate-400`, `white/5`, `red-300`, ...) or hex codes in `frontend/src/**/*.tsx`; hex
  codes only in `.ts` data files (the default person colour). Enforced by `npm run lint`.
- German and English for any new text. Public repo: no names or domains.

## Review Focus

1. A person whose `theme` is `None` (everyone after the migration) → `aurora` in `/api/me`, `/api/session` and
   `/api/apps/<key>/people`.
2. A new `family-hub-client` against an older hub that sends no `theme` → `HubPerson.theme == "aurora"`, no error.
3. `localStorage` unavailable (private mode, blocked storage) → `applyTheme` and `theme-init.js` still set
   `data-theme="aurora"` and never throw.
4. Logout, or the hub page loaded without a login → `data-theme` back to `aurora` (a shared iPad doesn't keep the
   last person's theme on the login screen).
5. The frontend Docker image built from the repo root doesn't pull in `venv/`, `node_modules/`, `e2e/.tmp` or the
   database (`.dockerignore` at the root).

---

### Task 1: Theme per person in the hub's API

**Files:**
- Modify: `backend/app/config.py` (`Theme = Literal["aurora"]`, `THEMES: tuple[str, ...] = ("aurora",)`,
  `DEFAULT_THEME = "aurora"`)
- Modify: `backend/app/models.py` (`Person.theme: Mapped[str | None] = mapped_column(String(20))`,
  `Person.theme_or_default` property)
- Create: `backend/app/migrations/versions/0009_person_theme.py` (add/drop column, as `0008`)
- Modify: `backend/app/schemas.py` (`PersonOut.theme: str`, `AppPerson.theme` with
  `AliasChoices("theme_or_default", "theme")`, `MePatch.theme: Theme | None = None`)
- Modify: `backend/app/login_api.py` (`PATCH /me` sets `theme` when sent, as `language`)
- Test: `tests/test_people.py`, `tests/test_session.py`, `tests/test_apps.py`

**Interfaces:**
- Produces: `/api/me`, `/api/session` `person`, `/api/apps/<key>/people` items gain `"theme": "aurora"`.

- [ ] **Step 1: Write the failing tests**
  - `test_people.py::test_own_theme`: logged in, `GET /api/me` → `theme == "aurora"`; `PATCH /api/me {"theme":
    "aurora"}` → 200 and `theme == "aurora"`; `{"theme": "daely"}` → 422.
  - `test_session.py`: the existing exact `person` dict gains `"theme": "aurora"`.
  - `test_apps.py`: one people-list item has `theme == "aurora"`.
- [ ] **Step 2: Run** `pytest tests/test_people.py tests/test_session.py tests/test_apps.py -q` → FAIL (no `theme`).
- [ ] **Step 3: Implement** as listed under Files.
- [ ] **Step 4: Run** `pytest -q` → PASS (includes `test_migrations.py::test_migration_matches_models`).
- [ ] **Step 5: Commit** `feat(hub): a theme per person, sent to the apps`

### Task 2: `family-hub-client` passes the theme on

**Files:**
- Modify: `client/family_hub_client/__init__.py` (`HubPerson.theme: str = "aurora"`, `_person` reads
  `data.get("theme") or "aurora"`)
- Modify: `client/family_hub_client/fake.py` (`add(..., theme: str = "aurora")`, `set_theme(name, theme)`,
  `_json` sends `theme`)
- Modify: `client/pyproject.toml` (version `1.2.0`), `client/README.md` (one line on `theme`)
- Test: `tests/test_client.py`

**Interfaces:**
- Produces: `HubPerson.theme: str`; `FakeHub.set_theme(name: str, theme: str) -> None`.

- [ ] **Step 1: Write the failing tests** in `tests/test_client.py`: the session answer with `"theme": "aurora"` →
  `person.theme == "aurora"`; an answer without `theme` (Review Focus 2) → `"aurora"`; the existing check that
  `FakeHub` answers as the hub does now covers `theme` (its dict includes it).
- [ ] **Step 2: Run** `pytest tests/test_client.py -q` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest -q` → PASS.
- [ ] **Step 5: Commit** `feat(client): pass the person's theme on to the apps`

### Task 3: The `family-hub-theme` package, used by the hub's frontend

**Files:**
- Create: `theme/package.json` (`"name": "family-hub-theme"`, `"version": "1.0.0"`, `"type": "module"`,
  `"exports": {".": {"types": "./index.d.ts", "default": "./index.js"}, "./theme.css": "./theme.css",
  "./theme-init.js": "./theme-init.js"}`, `"files"` the same plus `README.md`, license MIT, no dependencies)
- Create: `theme/theme.css` — `@theme` with every role from the spec's two role tables (colour roles as
  `--color-<role>`, plus `--radius-card`, `--radius-control`, `--shadow-card`, `--blur-glass`, `--font-sans`,
  `--page-glow`), Aurora values under `:root, [data-theme="aurora"]`; base styles (`body` background colour +
  `--page-glow`, font, colour), `.glass-card` and `.btn-primary` (gradient `button-from` → `button-to`) — moved from
  `frontend/src/index.css`.
- Create: `theme/index.js`, `theme/index.d.ts` — `export const THEMES: readonly string[]` (`["aurora"]`),
  `export const DEFAULT_THEME = "aurora"`, `export function applyTheme(name?: string | null): string` (sets
  `document.documentElement.dataset.theme` to `name` if in `THEMES`, else `aurora`; stores it in `localStorage`
  key `family-theme`, ignoring storage errors; returns the applied name).
- Create: `theme/theme-init.js` — a classic script: reads `family-theme` (in `try`), applies the same rule.
- Create: `theme/README.md` (install from the release URL, the two imports, the `index.html` script, `applyTheme`
  on login / logout, the roles).
- Modify: `frontend/package.json` (`"family-hub-theme": "file:../theme"`; scripts `"theme:copy": "node -e
  \"require('fs').copyFileSync('node_modules/family-hub-theme/theme-init.js','public/theme-init.js')\""`,
  `"predev"` and `"prebuild"` run it), `frontend/.gitignore` (`public/theme-init.js`)
- Modify: `frontend/index.html` (`<script src="/theme-init.js"></script>` first in `<head>`)
- Modify: `frontend/src/index.css` (`@import "tailwindcss"; @import "family-hub-theme/theme.css";` and only what is
  hub-specific)
- Modify: `frontend/Dockerfile` (paths for the repo-root context: copy `theme/` and `frontend/`, build in
  `frontend/`), `docker-compose.yml` (`frontend.build: {context: ., dockerfile: frontend/Dockerfile}`),
  `.github/workflows/ci-cd.yml` (frontend image: `context: .`, `file: frontend/Dockerfile`; backend unchanged)
- Create: `.dockerignore` at the root, used only by the frontend build (the backend keeps `./backend` as context):
  `**/node_modules`, `venv`, `**/__pycache__`, `backend`, `client`, `e2e`, `tests`, `docs`, `*.db`, `.git`
- Test: `frontend/src/theme.test.ts`

**Interfaces:**
- Produces: `applyTheme`, `THEMES`, `DEFAULT_THEME` from `family-hub-theme`; the CSS utilities `bg-page`,
  `bg-surface`, `bg-surface-strong`, `bg-field`, `border-line`, `border-line-strong`, `text-ink`, `text-muted`,
  `text-accent`, `text-accent-2`, `text-accent-3`, `text-success`, `text-danger`, `text-warning`, `bg-hover`,
  `bg-pressed`, `text-on-accent`, `rounded-card`, `rounded-control`, `shadow-card`, plus tinted state backgrounds
  as `bg-danger/15` etc. (Tailwind opacity on role colours).

- [ ] **Step 1: Write the failing tests** `frontend/src/theme.test.ts` (vitest in node; `document` and `localStorage`
  as small stubs via `vi.stubGlobal`, no jsdom dependency): `applyTheme("aurora")` →
  `"aurora"` and `dataset.theme === "aurora"` and storage holds it; `applyTheme("daely")` and `applyTheme(null)` →
  `"aurora"`; with `localStorage.setItem` throwing (Review Focus 3) → still `"aurora"`, no throw.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/theme.test.ts` → FAIL (package missing).
- [ ] **Step 3: Implement** the package and wire the hub frontend; `npm install` in `frontend/`.
- [ ] **Step 4: Run** `cd frontend && npm test && npm run build`, then `docker build -f frontend/Dockerfile .` and
  check the image has no `venv`/`node_modules` from the host (`docker run --rm <image> ls /usr/share/nginx/html`
  shows `theme-init.js`) → PASS.
- [ ] **Step 5: Commit** `feat(theme): the family-hub-theme package, used by the hub`

### Task 4: The hub's frontend on roles, and the person's theme applied

**Files:**
- Modify: `frontend/src/ui.ts` and every `.tsx` with palette classes (inventory: ~80 uses, mostly `text-slate-400`
  → `text-muted`, `text-white`/`text-slate-100/200/300` → `text-ink`, `bg-white/5` → `bg-hover`, `divide-white/5`
  → `divide-line`, red/amber/emerald → `danger`/`warning`/`success`, `text-blue-300` links → `text-accent`)
- Modify: `frontend/src/components/PeopleSettings.tsx`, `frontend/src/pages/Login.tsx` (`'#64748b'` →
  `DEFAULT_PERSON_COLOR` from a new `frontend/src/person.ts`)
- Create: `frontend/scripts/check-colors.mjs`; Modify: `frontend/package.json` (`lint` also runs it)
- Modify: `frontend/src/AuthContext.tsx` (`applyTheme(person.theme)` when `/api/me` answers;
  `applyTheme(null)` on logout and when nobody is logged in)
- Modify: `frontend/src/types.ts` (`Person.theme: string`)
- Modify: `frontend/src/pages/Settings.tsx` (theme select shown only when `THEMES.length > 1`, `PATCH /api/me
  {theme}`; texts `settings.theme` "Theme" / "Thema", `themes.aurora` "Aurora" / "Aurora")
- Test: `e2e/tests/theme.spec.ts`, `frontend/scripts/check-colors.mjs` self-check

**Interfaces:**
- Consumes: Task 1's `/api/me` `theme`; Task 3's package and utilities.

- [ ] **Step 1: Write the failing checks**
  - `e2e/tests/theme.spec.ts`: before login `html` has `data-theme="aurora"`; after login still `aurora`; after
    logout `aurora` (Review Focus 4); the Start page's cards have a computed `backdrop-filter` with `blur`.
  - `check-colors.mjs` with a `--self-test` flag: it flags `className="text-slate-400"`, `bg-white/5`,
    `'#123456'` in a `.tsx`, and passes `text-muted`, `bg-danger/15`, a hex in a `.ts` file.
- [ ] **Step 2: Run** `cd frontend && node scripts/check-colors.mjs --self-test` (FAIL: script missing) and
  `node scripts/check-colors.mjs` after writing it → FAIL listing today's ~80 uses.
- [ ] **Step 3: Implement** the replacements, `person.ts`, `AuthContext`, Settings, texts.
- [ ] **Step 4: Run** `cd frontend && npm run lint && npm test && npm run build`, `cd e2e && npm test` → PASS.
  Take before (from `main`) / after screenshots of Login, Start and Settings at phone and desktop width into the
  plan workspace for the PR.
- [ ] **Step 5: Commit** `feat(hub): the hub's pages use the theme's roles`

### Task 5: Publishing the package for the apps

**Files:**
- Create: `.github/workflows/theme-release.yml` — on push of tags `theme-v*`: check the tag matches
  `theme/package.json`'s version, `npm pack` in `theme/`, `gh release create <tag> family-hub-theme-<version>.tgz`
  (permissions `contents: write`).
- Modify: `.github/workflows/pr-checks.yml` (a `theme` job: `npm pack --dry-run` in `theme/` lists exactly the
  five files)
- Modify: `README.md` ("For apps": the theme package, its release URL
  `https://github.com/FrankAndreas/family-hub/releases/download/theme-v<version>/family-hub-theme-<version>.tgz`,
  and that the app's who-am-I answer returns `theme`)

- [ ] **Step 1: Run** `cd theme && npm pack --dry-run` → lists `package.json`, `theme.css`, `index.js`,
  `index.d.ts`, `theme-init.js`, `README.md`.
- [ ] **Step 2: Write the workflows and README.**
- [ ] **Step 3: Run** `python -c "import yaml,sys;[yaml.safe_load(open(f)) for f in sys.argv[1:]]"
  .github/workflows/theme-release.yml .github/workflows/pr-checks.yml` → no error.
- [ ] **Step 4: Commit** `ci(theme): publish the theme package as a release asset`
- [ ] **After merge (only with the user's OK):** push tag `theme-v1.0.0` and check the release has the `.tgz`.
