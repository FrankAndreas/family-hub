# Browser tests

Playwright starts its own backend (port 8110, fresh SQLite database and signing key in `e2e/.tmp`, Admin PIN
`1111`, `DEFAULT_LANGUAGE=en`, `COOKIE_INSECURE=1`) and frontend (port 3110, Vite forwarding `/api` to that backend),
so dev servers and their data are never touched. The backend runs through `serve.py`, with cheap PIN hashes as in the
backend tests.

Four tests run at a time against that one backend. So each test makes its own people and apps (`uniqueName`) and
never changes the Admin they all share (language, PIN, colour): a German Admin would break the tests alongside.

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
