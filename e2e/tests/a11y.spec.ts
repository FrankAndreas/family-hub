import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { ADMIN_PIN, logIn, uniqueName } from './helpers';

// Accessibility review 2026-11-08: axe finds nothing on any page or state, so a change that breaks a label, a
// landmark or a heading fails here. The buttons' contrast on their gradient axe can't measure (it says "incomplete"):
// index.css has the colours checked by hand
async function noViolations(page: Page, state: string) {
    const { violations } = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'])
        .analyze();
    expect(violations.map(v => `${v.id}: ${v.nodes.map(n => n.target.join(' ')).join(', ')}`), state).toEqual([]);
}

test('no accessibility violations before the login', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Admin', exact: true })).toBeVisible();
    await noViolations(page, 'names');
    await page.getByRole('button', { name: 'Admin', exact: true }).click();
    await page.getByLabel('PIN', { exact: true }).fill('0000');
    await expect(page.getByRole('alert')).toBeVisible();
    await noViolations(page, 'wrong PIN');

    // Links from the mails: a form, and a link that no longer works
    await page.goto('/reset-pin#token=made-up');
    await expect(page.getByLabel('New PIN', { exact: true })).toBeVisible();
    await noViolations(page, 'reset PIN');
    await page.goto('/reset-pin');
    await expect(page.getByRole('alert')).toBeVisible();
    await noViolations(page, 'reset PIN without token');
    await page.goto('/confirm-email#token=made-up');
    await expect(page.getByRole('alert')).toBeVisible();
    await noViolations(page, 'confirm e-mail');
});

test('no accessibility violations once logged in', async ({ page }) => {
    await logIn(page, 'Admin', ADMIN_PIN);
    await noViolations(page, 'start');
    await page.getByRole('link', { name: 'Settings' }).click();
    await expect(page.getByRole('heading', { name: 'My PIN' })).toBeVisible();
    await noViolations(page, 'settings');
    await page.getByRole('button', { name: '+ Add person' }).click();
    await noViolations(page, 'person form');
    await page.getByRole('button', { name: 'Cancel' }).click();
    await page.getByRole('button', { name: '+ Add app' }).click();
    await noViolations(page, 'app form');
});

// Screen readers: the tab names the page, moving to another page reads its heading, someone inactive says so
test('pages and people are announced', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle('Log in · Family');
    await logIn(page, 'Admin', ADMIN_PIN);
    await expect(page).toHaveTitle('Family');
    await page.getByRole('link', { name: 'Settings' }).click();
    await expect(page).toHaveTitle('Settings · Family');
    await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeFocused();
    await page.getByRole('link', { name: 'Start' }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Hello Admin' })).toBeFocused();

    const ole = uniqueName('Ole');
    await page.getByRole('link', { name: 'Settings' }).click();
    await page.getByRole('button', { name: '+ Add person' }).click();
    await page.getByLabel('Name', { exact: true }).fill(ole);
    await page.getByLabel('PIN of the person', { exact: true }).fill('1357');
    await page.getByRole('button', { name: 'Save person' }).click();
    await page.getByRole('button', { name: `Edit ${ole}` }).click();
    await page.getByLabel('Active').uncheck();
    await page.getByRole('button', { name: 'Save person' }).click();
    await expect(page.getByRole('listitem').filter({ hasText: ole })).toContainText(`${ole}inactive`);
    await noViolations(page, 'inactive person');
});
