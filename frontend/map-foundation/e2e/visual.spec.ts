import { expect, test } from '@playwright/test';

test('Stage 26E foundation visual baseline at 1440x900', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/map-foundation/index.html');
  await expect(page.getByTestId('foundation-ready')).toHaveText('ready', { timeout: 30_000 });
  await expect(page).toHaveScreenshot('stage-26e-foundation-1440x900.png', {
    animations: 'disabled',
    caret: 'hide',
    fullPage: true,
    maxDiffPixelRatio: 0.01,
  });
});
