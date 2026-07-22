import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('Stage 26E foundation has no detectable WCAG A/AA violations', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/map-foundation/index.html');
  await expect(page.getByTestId('foundation-ready')).toHaveText('ready', { timeout: 30_000 });
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(results.violations).toEqual([]);
});
