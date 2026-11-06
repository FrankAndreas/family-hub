import { expect, test } from '@playwright/test';
import { ADMIN_PIN, logIn, uniqueName } from './helpers';

// The hub out of reach at home: the login says so and tries again, instead of "not in the family list"
test('login while the hub is out of reach', async ({ page }) => {
    let down = true;
    await page.route('**/api/people/public', route => (down ? route.abort() : route.fallback()));
    await page.goto('/');
    await expect(page.getByRole('alert')).toHaveText('No connection to the server.');
    await expect(page.getByText('Not in the family list')).toHaveCount(0);
    down = false;
    await page.getByRole('button', { name: 'Try again' }).click();
    await expect(page.getByRole('button', { name: 'Admin', exact: true })).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
});

// The own PIN is typed twice; two different ones change nothing
test('own PIN: the new one twice', async ({ page }) => {
    const ben = uniqueName('Ben');
    await logIn(page, 'Admin', ADMIN_PIN);
    await page.getByRole('link', { name: 'Settings' }).click();
    await page.getByRole('button', { name: '+ Add person' }).click();
    await page.getByLabel('Name', { exact: true }).fill(ben);
    await page.getByLabel('PIN of the person', { exact: true }).fill('4826');
    await page.getByRole('button', { name: 'Save person' }).click();
    await expect(page.getByRole('listitem').filter({ hasText: ben })).toBeVisible();
    await page.getByRole('button', { name: 'Log out', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Who are you?' })).toBeVisible();

    await logIn(page, ben, '4826');
    await page.getByRole('link', { name: 'Settings' }).click();
    await page.getByLabel('Current PIN', { exact: true }).fill('4826');
    await page.getByLabel('New PIN', { exact: true }).fill('7391');
    await page.getByLabel('New PIN again', { exact: true }).fill('7392');
    await page.getByRole('button', { name: 'Change PIN' }).click();
    await expect(page.getByText("The two PINs don't match.")).toBeVisible();
    await page.getByLabel('New PIN again', { exact: true }).fill('7391');
    await page.getByRole('button', { name: 'Change PIN' }).click();
    await expect(page.getByText('PIN changed.', { exact: false })).toBeVisible();
});

// A language change that fails says so
test('language change that fails', async ({ page }) => {
    await logIn(page, 'Admin', ADMIN_PIN);
    await page.getByRole('link', { name: 'Settings' }).click();
    await page.route('**/api/me', route => (route.request().method() === 'PATCH' ? route.abort() : route.fallback()));
    await page.getByLabel('Language').selectOption('de');
    await expect(page.getByRole('alert')).toHaveText('No connection to the server.');
    await expect(page.getByLabel('Language')).toHaveValue('en');
});
