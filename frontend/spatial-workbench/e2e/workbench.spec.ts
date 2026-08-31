import { expect, test } from '@playwright/test';

for (const viewport of [{ width: 1280, height: 720 }, { width: 1440, height: 900 }]) {
  test(`isolated lifecycle and controls at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto('/spatial-workbench/index.html');
    await expect(page.getByRole('heading', { name: /Stage 27B/ })).toBeVisible();
    await expect(page.getByText('Development-only · no production route wiring')).toBeVisible();
    await expect(page.getByTestId('backend')).toContainText(/webgpu|webgl2/, { timeout: 30_000 });
    await page.getByRole('button', { name: 'Restrained pitch' }).click();
    await page.getByRole('button', { name: 'Top-down' }).click();
    await page.getByRole('button', { name: 'Suspend' }).click();
    await page.getByRole('button', { name: 'Resume' }).click();
    await page.getByRole('button', { name: 'Compare picking candidates' }).click();
    await expect(page.getByText('babylon-instance')).toBeVisible();
    await expect(page.getByTestId('telemetry')).toContainText(`"visibleCount": 20000`);
  });
}
