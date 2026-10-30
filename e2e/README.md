# Browser tests

Playwright starts its own backend (port 8110, fresh SQLite database and signing key in `e2e/.tmp`, Admin PIN
`1111`, `DEFAULT_LANGUAGE=en`, `COOKIE_INSECURE=1`) and frontend (port 3110, Vite forwarding `/api` to that backend),
so dev servers and their data are never touched.

```bash
cd e2e
npm install
npx playwright install chromium
E2E_PYTHON=../venv/bin/python npm test
```

`E2E_PYTHON` is the Python that has the backend's packages. Projects: `tablet` (1180×820) runs everything; `phone`
runs `phone.spec.ts`.

| Spec | What it shows |
|---|---|
| `hub.spec.ts` | Admin adds a person and an app; the start page links to the app; the person logs in with their PIN and sees no people or app settings; a wrong PIN; `?next=` only back to an app on the start page |
| `phone.spec.ts` | the start page and the settings fit a phone |
