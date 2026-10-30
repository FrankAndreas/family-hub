import { expect, test, type Page } from '@playwright/test';
import { ADMIN_PIN, lastResetLink, logIn, uniqueName } from './helpers';

async function addParent(page: Page, name: string, pin: string) {
    await page.getByRole('link', { name: 'Settings' }).click();
    await page.getByRole('button', { name: '+ Add person' }).click();
    await page.getByLabel('Name', { exact: true }).fill(name);
    await page.getByRole('combobox', { name: /^Role/ }).selectOption('PARENT');
    await page.getByLabel('PIN of the person', { exact: true }).fill(pin);
    await page.getByRole('button', { name: 'Save person' }).click();
    await expect(page.getByRole('listitem').filter({ hasText: name })).toContainText('Parent');
}

async function logOut(page: Page) {
    await page.getByRole('button', { name: 'Log out', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Who are you?' })).toBeVisible();
}

// A parent gives themselves an e-mail address (with their PIN), forgets the PIN and sets a new one through the mail
test('forgot PIN by e-mail', async ({ page }) => {
    const mia = uniqueName('Mia');
    const email = `${mia.toLowerCase()}@example.org`;
    await logIn(page, 'Admin', ADMIN_PIN);
    await addParent(page, mia, '3579');
    await logOut(page);

    await logIn(page, mia, '3579');
    await page.getByRole('link', { name: 'Settings' }).click();
    await page.getByRole('button', { name: `Edit ${mia}` }).click();
    await page.getByLabel('E-mail', { exact: true }).fill(email);
    await page.getByLabel('Your current PIN (to change your e-mail address)').fill('3579');
    await page.getByRole('button', { name: 'Save person' }).click();
    await expect(page.getByRole('listitem').filter({ hasText: mia })).toContainText(email);
    await logOut(page);

    await page.getByRole('button', { name: mia, exact: true }).click();
    await page.getByRole('button', { name: 'Forgot PIN?' }).click();
    await expect(page.getByRole('status')).toHaveText('If an e-mail address is registered, a link is on its way.');

    await page.goto(lastResetLink(email));
    await page.getByLabel('New PIN', { exact: true }).fill('2222');
    await page.getByLabel('New PIN again', { exact: true }).fill('2222');
    await page.getByRole('button', { name: 'Set PIN' }).click();
    await page.getByRole('link', { name: 'To the login' }).click();
    await logIn(page, mia, '2222');
});

// Each parent changes only themselves and the children
test('other parents are read-only', async ({ page }) => {
    const ben = uniqueName('Ben');
    await logIn(page, 'Admin', ADMIN_PIN);
    await addParent(page, ben, '4680');
    await expect(page.getByRole('button', { name: `Edit ${ben}` })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Edit Admin' })).toBeVisible();
});

// An app's "Log out" goes to /logout?next=<app>: the login ends, and the next login goes back to the app
test('logout with next', async ({ page, baseURL }) => {
    const app = uniqueName('Back');
    await logIn(page, 'Admin', ADMIN_PIN);
    await page.getByRole('link', { name: 'Settings' }).click();
    await page.getByRole('button', { name: '+ Add app' }).click();
    await page.getByLabel('App name', { exact: true }).fill(app);
    await page.getByLabel('Address at home', { exact: true }).fill(`${baseURL}/`);
    await page.getByRole('button', { name: 'Save app' }).click();
    await expect(page.getByRole('listitem').filter({ hasText: app })).toBeVisible();

    await page.goto(`/logout?next=${encodeURIComponent(`${baseURL}/settings`)}`);
    await expect(page.getByRole('heading', { name: 'Who are you?' })).toBeVisible();
    await page.getByRole('button', { name: 'Admin', exact: true }).click();
    await page.getByLabel('PIN', { exact: true }).fill(ADMIN_PIN);
    await page.getByRole('button', { name: 'Log in' }).click();
    await expect(page).toHaveURL(`${baseURL}/settings`);
});

// Security review 2026-10-30, finding 7: who-is-logged-in, asked as the logout page opens, may answer after the logout;
// it must not bring the person back
test('a late answer doesn\'t undo the logout', async ({ page }) => {
    await logIn(page, 'Admin', ADMIN_PIN);
    // The server answers "who is logged in" before the logout reaches it, and the answer arrives only after it
    await page.route('**/api/logout', async route => {
        await new Promise(resolve => setTimeout(resolve, 500));
        await route.continue();
    });
    await page.route('**/api/me', async route => {
        const response = await route.fetch();
        await new Promise(resolve => setTimeout(resolve, 1500));
        await route.fulfill({ response });
    });
    await page.goto('/logout');
    await expect(page.getByRole('heading', { name: 'Who are you?' })).toBeVisible();
    await page.waitForTimeout(2000);
    await expect(page.getByRole('heading', { name: 'Who are you?' })).toBeVisible();
});
