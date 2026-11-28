# family-hub-theme

The family apps' look, by role: components use `bg-surface`, `text-muted`, `rounded-card`, ... and never palette
colours, so a theme is one set of values here (themes design 2026-11-28 in family-hub). Each person picks their
theme in the hub; the app gets it with the person (`family-hub-client`'s `HubPerson.theme`). Themes: `aurora`.

## Install

The apps' images have no git and npm can't install a folder of a GitHub archive, so each version is a release asset
(immutable), in `frontend/package.json`:

```json
"family-hub-theme": "https://github.com/FrankAndreas/family-hub/releases/download/theme-v1.0.0/family-hub-theme-1.0.0.tgz"
```

## Use

- CSS entry: `@import "tailwindcss"; @import "family-hub-theme/theme.css";` (sets `body`, `.glass-card`,
  `.btn-primary` and the role utilities).
- `index.html`, first in `<head>`: `<script src="/theme-init.js"></script>`, with
  `"theme:copy": "node -e \"require('fs').copyFileSync('node_modules/family-hub-theme/theme-init.js','public/theme-init.js')\""`
  run by `predev` and `prebuild` (and `public/theme-init.js` in `.gitignore`). It shows the remembered theme before the
  page renders; a file, since the apps' Content-Security-Policy allows no inline scripts.
- When the app learns who is logged in: `applyTheme(me.theme)`; on logout or without a login: `applyTheme(null)`.
  Unknown themes (a newer hub) show `aurora`.
- Keep palette colours out: copy family-hub's `frontend/scripts/check-colors.mjs` into the app's `lint`.

## Roles

Colours (`bg-*`, `text-*`, `border-*`, ..., with opacity like `bg-danger/15`): `page`, `surface`, `surface-strong`,
`field`, `line`, `line-strong`, `ink`, `muted`, `accent`, `accent-2`, `accent-3`, `success`, `danger`, `warning`,
`on-accent`, `hover`, `pressed`, `button-from`, `button-to`. Shapes: `rounded-card`, `rounded-control`,
`shadow-card`, `backdrop-blur-glass`; font `font-sans`. A person's own colour and chart series colours are data, not
roles.

## A new version

Change `package.json`'s version, merge, then push the tag `theme-v<version>`: the release workflow packs this folder
and attaches the `.tgz` to the release.
