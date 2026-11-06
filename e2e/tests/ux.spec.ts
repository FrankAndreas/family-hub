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
    await expect(page.getByRole('alert')).toHaveText("The two PINs don't match.");
    await page.getByLabel('New PIN again', { exact: true }).fill('7391');
    await page.getByRole('button', { name: 'Change PIN' }).click();
    await expect(page.getByRole('status')).toContainText('PIN changed.');
    // Typing again clears it
    await page.getByLabel('Current PIN', { exact: true }).fill('7');
    await expect(page.getByRole('status')).toHaveCount(0);
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

// The page one is on stands out in the navigation
test('navigation marks the current page', async ({ page }) => {
    await logIn(page, 'Admin', ADMIN_PIN);
    await expect(page.getByRole('link', { name: 'Start' })).toHaveAttribute('aria-current', 'page');
    await page.getByRole('link', { name: 'Settings' }).click();
    await expect(page.getByRole('link', { name: 'Settings' })).toHaveAttribute('aria-current', 'page');
    await expect(page.getByRole('link', { name: 'Start' })).not.toHaveAttribute('aria-current', 'page');
});

// "Edit" opens the form with the cursor in it; while it is open no other "Edit" can throw its input away
test('one edit form at a time', async ({ page }) => {
    const ola = uniqueName('Ola');
    await logIn(page, 'Admin', ADMIN_PIN);
    await page.getByRole('link', { name: 'Settings' }).click();
    await page.getByRole('button', { name: '+ Add person' }).click();
    await expect(page.getByLabel('Name', { exact: true })).toBeFocused();
    await page.getByLabel('Name', { exact: true }).fill(ola);
    await page.getByLabel('E-mail', { exact: true }).fill(`${ola.toLowerCase()}@example.org`);
    await expect(page.getByText('The address counts once the person opens the link')).toBeVisible();
    await page.getByLabel('PIN of the person', { exact: true }).fill('3141');
    await page.getByRole('button', { name: 'Save person' }).click();

    await page.getByRole('button', { name: `Edit ${ola}` }).click();
    await expect(page.getByLabel('Name', { exact: true })).toBeFocused();
    await expect(page.getByLabel('Name', { exact: true })).toBeInViewport();
    await expect(page.getByLabel('Active')).toHaveAccessibleDescription(/logged out everywhere/);
    await expect(page.getByRole('button', { name: 'Edit Admin' })).toBeDisabled();
    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByRole('button', { name: 'Edit Admin' })).toBeEnabled();
});

// The app key's format is described, so the browser's own message helps
test('app key format', async ({ page }) => {
    await logIn(page, 'Admin', ADMIN_PIN);
    await page.getByRole('link', { name: 'Settings' }).click();
    await page.getByRole('button', { name: '+ Add app' }).click();
    await expect(page.getByLabel('App name', { exact: true })).toBeFocused();
    await expect(page.getByLabel('App key', { exact: true })).toHaveAttribute('title', /Lowercase letters, digits and hyphens/);
});

// The tab's title follows the language: the browser's before the login, the person's after it
test('tab title per language', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle('Family');
    await logIn(page, 'Admin', ADMIN_PIN);
    await page.getByRole('link', { name: 'Settings' }).click();
    await page.getByLabel('Language').selectOption('de');
    await expect(page).toHaveTitle('Familie');
    await page.getByLabel('Sprache').selectOption('en');
    await expect(page).toHaveTitle('Family');
});

// A reset link without its token says so at once, without a form to fill in first
test('reset link without a token', async ({ page }) => {
    await page.goto('/reset-pin');
    await expect(page.getByRole('alert')).toHaveText('This link is invalid or has expired. Ask for a new one.');
    await expect(page.getByLabel('New PIN', { exact: true })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'To the login' })).toBeVisible();
});
