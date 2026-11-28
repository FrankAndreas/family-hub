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
    // The theme's roles reach the page: glass cards with their blur
    const blur = await page.locator('.glass-card').first().evaluate(e => getComputedStyle(e).backdropFilter);
    expect(blur).toContain('blur');
    await page.evaluate(() => localStorage.setItem('family-theme', 'stale'));
    await page.getByRole('button', { name: 'Log out' }).click();
    await expect(page.getByRole('heading', { name: 'Who are you?' })).toBeVisible();
    await expect(html).toHaveAttribute('data-theme', 'aurora');
    await expect.poll(() => remembered(page)).toBe('aurora');
});
