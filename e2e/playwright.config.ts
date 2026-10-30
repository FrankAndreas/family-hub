import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';
import { OUTBOX, PYTHON as python } from './tests/helpers';

// The tests start their own backend (fresh SQLite database, Admin PIN 1111) and frontend on ports of their own, so a
// dev server on 8000/5173 and its data are never touched. E2E_PYTHON: the Python with the backend's packages.
export const BACKEND = 'http://localhost:8110';
export const FRONTEND = 'http://localhost:3110';
const data = path.resolve(__dirname, '.tmp');

export default defineConfig({
    testDir: './tests',
    // One backend and database for all tests
    workers: 1,
    retries: process.env.CI ? 1 : 0,
    reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
    use: {
        baseURL: FRONTEND,
        // The tests find elements by their English texts
        locale: 'en-US',
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
    },
    projects: [
        { name: 'tablet', use: { ...devices['Desktop Chrome'], viewport: { width: 1180, height: 820 } } },
        { name: 'phone', use: { ...devices['Pixel 7'] }, testMatch: /phone\.spec\.ts/ },
    ],
    webServer: [
        {
            command: `rm -rf "${data}" && mkdir -p "${data}" && "${python}" -m uvicorn app.main:app --port 8110`,
            cwd: path.resolve(__dirname, '..', 'backend'),
            url: `${BACKEND}/health`,
            env: {
                DATABASE_URL: `sqlite:///${data}/e2e.db`,
                DATA_DIR: data,
                INITIAL_ADMIN_PIN: '1111',
                DEFAULT_LANGUAGE: 'en',
                // Plain http in the tests: a Secure cookie would never come back
                COOKIE_INSECURE: '1',
                // "Forgot PIN" on, with the mails written to a file the tests read instead of sent (never on the NAS)
                RESEND_API_KEY: 'test',
                MAIL_FROM: 'hub@example.org',
                HUB_PUBLIC_URL: FRONTEND,
                MAIL_OUTBOX: OUTBOX,
            },
            reuseExistingServer: false,
            timeout: 60_000,
        },
        {
            // Vite forwards /api to the test backend, so the login cookie is the page's own (as with nginx)
            command: 'npx vite --port 3110 --strictPort',
            cwd: path.resolve(__dirname, '..', 'frontend'),
            url: FRONTEND,
            env: { API_PROXY: BACKEND },
            reuseExistingServer: false,
            timeout: 60_000,
        },
    ],
});
