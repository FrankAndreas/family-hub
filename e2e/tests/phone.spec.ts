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

// On a touch screen the small buttons in the lists are finger-sized (44 px); with a mouse they stay as they are
test('finger-sized buttons on touch screens', async ({ page }) => {
    await logIn(page, 'Admin', ADMIN_PIN);
    await page.getByRole('link', { name: 'Settings' }).click();
    const coarse = await page.evaluate(() => matchMedia('(pointer: coarse)').matches);
    expect(coarse).toBe(test.info().project.name === 'phone');
    for (const target of [page.getByRole('button', { name: 'Edit Admin' }), page.getByRole('link', { name: 'Start' })]) {
        const box = (await target.boundingBox())!;
        if (coarse) {
            expect(box.height).toBeGreaterThanOrEqual(44);
            expect(box.width).toBeGreaterThanOrEqual(44);
        } else {
            expect(box.height).toBeLessThan(44);
        }
    }
});
