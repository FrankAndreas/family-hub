import { expect, test } from '@playwright/test';
import { ADMIN_PIN, logIn } from './helpers';

// The start page and the settings fit a phone
test('fits a phone', async ({ page }) => {
    await logIn(page, 'Admin', ADMIN_PIN);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
    await page.getByRole('link', { name: 'Settings' }).click();
    await expect(page.getByRole('heading', { name: 'My PIN' })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
});
