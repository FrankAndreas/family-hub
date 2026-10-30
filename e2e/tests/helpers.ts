import fs from 'node:fs';
import path from 'node:path';
import { expect, type Page } from '@playwright/test';

// The Python with the backend's packages; a path is made absolute (Python warns about relative ones with "..")
const configured = process.env.E2E_PYTHON ?? 'python3';
export const PYTHON = configured.includes('/') ? path.resolve(configured) : configured;

export const ADMIN_PIN = '1111';

// The hub writes its mails here in the tests (MAIL_OUTBOX) instead of sending them
export const OUTBOX = path.resolve(__dirname, '..', '.tmp', 'outbox.jsonl');

// The link to this page (reset-pin, confirm-email) in the last such mail to this address
export function lastLink(to: string, page: 'reset-pin' | 'confirm-email'): string {
    const mails = fs.readFileSync(OUTBOX, 'utf-8').trim().split('\n').map(line => JSON.parse(line) as { to: string[]; text: string });
    const pattern = new RegExp(`http\\S+/${page}#token=\\S+`);
    const link = mails.reverse().map(m => m.to.includes(to) ? m.text.match(pattern)?.[0] : undefined).find(Boolean);
    if (!link) throw new Error(`no ${page} link for ${to}`);
    return link;
}

// People of a test's own (one database for all tests); invented names only
export const uniqueName = (prefix: string) => `${prefix}${Date.now().toString(36).slice(-4)}${Math.random().toString(36).slice(2, 5)}`;

export async function logIn(page: Page, name: string, pin: string) {
    await page.goto('/');
    await page.getByRole('button', { name, exact: true }).click();
    await page.getByLabel('PIN', { exact: true }).fill(pin);
    await page.getByRole('button', { name: 'Log in' }).click();
    await expect(page.getByRole('heading', { name: `Hello ${name}` })).toBeVisible();
}
