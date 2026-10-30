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
