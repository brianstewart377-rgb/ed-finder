import { test, expect } from '@playwright/test';

async function firstSeededSystem(page: import('@playwright/test').Page) {
  const response = await page.request.post('/api/local/search', {
    data: {
      reference_coords: { x: 0, y: 0, z: 0 },
      filters: { distance: { min: 0, max: 1000 } },
      size: 1,
    },
  });
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.results.length).toBeGreaterThan(0);
  return body.results[0] as { id64: number; name: string };
}

test.describe('Stage 25C selected-system continuity', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => localStorage.clear());
  });

  test('Finder context is non-modal and direct Planner entry requires an explicit draft', async ({ page }) => {
    const system = await firstSeededSystem(page);

    await page.goto(`/#finder/context/${system.id64}`);
    await expect(page.getByTestId('selected-system-context-bar')).toBeVisible();
    await expect(page.getByTestId('selected-system-context-name')).toContainText(system.name);
    await expect(page.getByTestId('selected-system-context-posture')).toContainText('System detail available');
    await expect(page.getByTestId('selected-system-context-id64')).toContainText(String(system.id64));
    await expect(page.getByTestId('system-detail-modal')).toHaveCount(0);

    await page.goto(`/#colony-planner/system/${system.id64}`);
    await expect(page.getByTestId('planner-no-active-draft-route')).toBeVisible();
    await expect(page.getByTestId('planner-selected-system-context')).toContainText(system.name);
    await expect(page.getByTestId('planner-selected-system-context')).toContainText(`ID64 ${system.id64}`);
    await expect(page.getByTestId('planner-create-draft')).toBeVisible();

    await page.getByTestId('planner-create-draft').click();
    await expect(page).toHaveURL(new RegExp(`#colony-planner/system/${system.id64}/project/`));
  });

  test('an invalid selected-system link shows recovery without a stale context bar', async ({ page }) => {
    await page.goto('/#finder/context/not-a-number');
    await expect(page.getByTestId('selected-system-context-error')).toBeVisible();
    await expect(page.getByTestId('selected-system-context-bar')).toHaveCount(0);

    await page.getByTestId('selected-system-context-recover').click();
    await expect(page).toHaveURL(/#finder$/);
  });
});
