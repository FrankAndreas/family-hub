import { expect, test } from '@playwright/test';
import { ADMIN_PIN, logIn } from './helpers';

// Themes (design 2026-11-28): the page carries the person's theme from who is logged in; logged out, the default
const remembered = (page: import('@playwright/test').Page) => page.evaluate(() => localStorage.getItem('family-theme'));

test('the page applies the person theme, and the default after logout', async ({ page }) => {
    const html = page.locator('html');
    await page.goto('/');
    await expect(html).toHaveAttribute('data-theme', 'aurora');
    await page.evaluate(() => localStorage.removeItem('family-theme'));
    await logIn(page, 'Admin', ADMIN_PIN);
    await expect(html).toHaveAttribute('data-theme', 'aurora');
    // Applied (and remembered) from who is logged in, not only from the last page load
    await expect.poll(() => remembered(page)).toBe('aurora');
    // The theme's roles reach the page: glass cards with their blur (Settings always has cards; Start may have none)
    await page.getByRole('link', { name: 'Settings' }).click();
    const blur = await page.locator('.glass-card').first().evaluate(e => getComputedStyle(e).backdropFilter);
    expect(blur).toContain('blur');
    await page.evaluate(() => localStorage.setItem('family-theme', 'stale'));
    await page.getByRole('button', { name: 'Log out', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Who are you?' })).toBeVisible();
    await expect(html).toHaveAttribute('data-theme', 'aurora');
    await expect.poll(() => remembered(page)).toBe('aurora');
});

// The remembered theme is set before the page renders by a file the page loads first (no inline scripts allowed)
test('the page loads theme-init.js', async ({ request }) => {
    const response = await request.get('/theme-init.js');
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toContain('javascript');
    expect(await response.text()).toContain('family-theme');
});

// The theme's base and component styles sit in Tailwind's layers, so an app's utilities win over them
test('utilities override the theme components', async ({ page }) => {
    await page.goto('/');
    const person = page.getByRole('button', { name: 'Admin', exact: true });
    const background = () => person.evaluate(e => getComputedStyle(e).backgroundColor);
    const before = await background();
    await person.hover();
    await expect.poll(background).not.toBe(before);
});

// The inactive page link is quieter than the active one and lights up on hover
test('the navigation shows which link is active and where the pointer is', async ({ page }) => {
    await logIn(page, 'Admin', ADMIN_PIN);
    const color = (name: string) => page.getByRole('link', { name, exact: true }).evaluate(e => getComputedStyle(e).color);
    const active = await color('Start');
    const inactive = await color('Settings');
    expect(inactive).not.toBe(active);
    await page.getByRole('link', { name: 'Settings', exact: true }).hover();
    await expect.poll(() => color('Settings')).toBe(active);
});
