import { expect, test } from '@playwright/test';
import { ADMIN_PIN, logIn, uniqueName } from './helpers';

// Admin adds a person and a tile; the start page shows the tile; the person logs in with their own PIN
test('people, tiles and the start page', async ({ page }) => {
    await logIn(page, 'Admin', ADMIN_PIN);
    await page.getByRole('link', { name: 'Settings' }).click();

    const lena = uniqueName('Lena');
    await page.getByRole('button', { name: '+ Add person' }).click();
    await page.getByLabel('Name', { exact: true }).fill(lena);
    await page.getByLabel('E-mail', { exact: true }).fill(`${lena.toLowerCase()}@example.ch`);
    await page.getByLabel('PIN of the person', { exact: true }).fill('2468');
    await page.getByRole('button', { name: 'Save person' }).click();
    await expect(page.getByRole('listitem').filter({ hasText: lena })).toContainText('Child');

    const app = uniqueName('Essen');
    await page.getByRole('button', { name: '+ Add app' }).click();
    await page.getByLabel('App name', { exact: true }).fill(app);
    await page.getByLabel('Icon', { exact: true }).fill('🍲');
    await page.getByLabel('Address at home', { exact: true }).fill('https://essen.local.example.ch');
    await page.getByRole('button', { name: 'Save app' }).click();
    await expect(page.getByRole('listitem').filter({ hasText: app })).toContainText('home only');

    await page.getByRole('link', { name: 'Start' }).click();
    const tile = page.getByRole('link', { name: new RegExp(app) });
    await expect(tile).toHaveAttribute('href', 'https://essen.local.example.ch');

    await page.getByRole('button', { name: 'Log out' }).click();
    // Wait for the logout to reach the server before logIn() loads the page again
    await expect(page.getByRole('heading', { name: 'Who are you?' })).toBeVisible();
    await logIn(page, lena, '2468');
    await expect(page.getByRole('link', { name: new RegExp(app) })).toBeVisible();
    // Children don't manage people or apps
    await page.getByRole('link', { name: 'Settings' }).click();
    await expect(page.getByRole('heading', { name: 'My PIN' })).toBeVisible();
    await expect(page.getByRole('button', { name: '+ Add person' })).toHaveCount(0);
});

// A wrong PIN says so and stays on the login screen
test('wrong PIN', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Admin', exact: true }).click();
    await page.getByLabel('PIN', { exact: true }).fill('0000');
    await page.getByRole('button', { name: 'Log in' }).click();
    await expect(page.getByText('Wrong name or PIN')).toBeVisible();
});

// An app sends people to the hub's login with ?next=; back they go only to an app on the start page
test('back to the app after logging in', async ({ page }) => {
    await page.goto('/?next=https://evil.example.com/');
    await page.getByRole('button', { name: 'Admin', exact: true }).click();
    await page.getByLabel('PIN', { exact: true }).fill(ADMIN_PIN);
    await page.getByRole('button', { name: 'Log in' }).click();
    // Not an app of the family: stays on the start page
    await expect(page.getByRole('heading', { name: 'Hello Admin' })).toBeVisible();
});

// An app that uses the family login shows only for the people allowed to use it
test('access per app', async ({ page }) => {
    await logIn(page, 'Admin', ADMIN_PIN);
    await page.getByRole('link', { name: 'Settings' }).click();

    const mia = uniqueName('Mia');
    await page.getByRole('button', { name: '+ Add person' }).click();
    await page.getByLabel('Name', { exact: true }).fill(mia);
    await page.getByLabel('PIN of the person', { exact: true }).fill('1357');
    await page.getByRole('button', { name: 'Save person' }).click();
    await expect(page.getByRole('listitem').filter({ hasText: mia })).toBeVisible();

    const app = uniqueName('Geld');
    await page.getByRole('button', { name: '+ Add app' }).click();
    await page.getByLabel('App name', { exact: true }).fill(app);
    await page.getByLabel('Address at home', { exact: true }).fill('https://geld.local.example.ch');
    await page.getByLabel('App key', { exact: true }).fill(`k${Math.random().toString(36).slice(2, 8).replace(/[^a-z]/g, 'x')}`);
    const who = page.getByRole('group', { name: 'Who may use it' });
    await who.getByLabel('Admin', { exact: true }).check();
    await page.getByRole('button', { name: 'Save app' }).click();
    await expect(page.getByRole('listitem').filter({ hasText: app })).toContainText('1 person');

    await page.getByRole('button', { name: 'Log out', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Who are you?' })).toBeVisible();
    await logIn(page, mia, '1357');
    await expect(page.getByRole('link', { name: new RegExp(app) })).toHaveCount(0);
    await page.getByRole('button', { name: 'Log out', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Who are you?' })).toBeVisible();
    await logIn(page, 'Admin', ADMIN_PIN);
    await expect(page.getByRole('link', { name: new RegExp(app) })).toBeVisible();
});

// An app's Cloudflare Access application (hub#12): its AUD tag is kept, and shown again when editing the app
test('the AUD tag of an app', async ({ page }) => {
    await logIn(page, 'Admin', ADMIN_PIN);
    await page.getByRole('link', { name: 'Settings' }).click();
    const app = uniqueName('Essen');
    const tag = 'ab'.repeat(32);
    await page.getByRole('button', { name: '+ Add app' }).click();
    await page.getByLabel('App name', { exact: true }).fill(app);
    await page.getByLabel('Address at home', { exact: true }).fill('https://essen.local.example.ch');
    await page.getByLabel('App key', { exact: true }).fill(`k${Math.random().toString(36).slice(2, 8).replace(/[^a-z]/g, 'x')}`);
    await page.getByLabel("Cloudflare Access: the AUD tag of this app's application").fill(tag.toUpperCase());
    await page.getByRole('button', { name: 'Save app' }).click();
    await page.getByRole('button', { name: `Edit ${app}` }).click();
    await expect(page.getByLabel("Cloudflare Access: the AUD tag of this app's application")).toHaveValue(tag);
});
