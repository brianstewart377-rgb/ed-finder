import { expect, test } from '@playwright/test';

const viewports = [{ width: 1280, height: 720 }, { width: 1440, height: 900 }];

for (const viewport of viewports) {
  test(`typed foundation compatibility at ${viewport.width}x${viewport.height}`, async ({ page, browserName }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.setViewportSize(viewport);
    await page.goto('/map-foundation/index.html');
    await expect(page.getByTestId('foundation-ready')).toHaveText('ready', { timeout: 30_000 });
    await expect(page.locator('canvas')).toBeVisible();
    await expect(page.locator('.map-foundation-labels span').first()).toBeVisible();

    const guaranteed = page.getByRole('complementary', { name: 'Map keyboard companion' })
      .getByRole('button').first();
    await guaranteed.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('last-host-command')).toHaveText('selectSystem');

    await page.getByLabel('Return from feature').selectOption('clusterSearch');
    await expect(page.getByTestId('return-workflow')).toHaveText('clusterSearch');
    const snapshot = await page.evaluate(() => window.__stage26cFoundation!.snapshot());
    expect(snapshot.regionLabelCount).toBe(42);
    expect(snapshot.visible.returnedBackground).toBeLessThanOrEqual(25_000);
    expect(snapshot.clusterCount).toBeGreaterThan(0);
    expect(errors, `${browserName} emitted page errors`).toEqual([]);
  });
}
