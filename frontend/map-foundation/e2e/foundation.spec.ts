import { expect, test } from '@playwright/test';

const viewports = [{ width: 1280, height: 720 }, { width: 1440, height: 900 }];

for (const viewport of viewports) {
  test(`region-first foundation at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
    await page.setViewportSize(viewport);
    await page.goto('/map-foundation/index.html');
    await expect(page.getByTestId('foundation-ready')).toHaveText('ready', { timeout: 30_000 });

    const initial = await page.evaluate(() => window.__stage26cFoundation!.snapshot());
    expect(initial.datasetSize).toBe(500_000);
    expect(initial.regionLabelCount).toBe(42);
    expect(initial.regionBoundaryCount).toBeGreaterThan(0);
    expect(initial.visible.returnedBackground).toBeLessThanOrEqual(25_000);
    expect(initial.visible.truncated).toBe(true);
    expect(initial.visible.guaranteedCount).toBe(5);
    expect(initial.highlightCount).toBe(5);
    expect(initial.clusterCount).toBe(1);

    const canvas = page.locator('canvas');
    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();
    if (!box) return;
    const target = { x: box.width / 2 + 250, y: box.height / 2 };
    await canvas.click({ position: target });
    await expect(page.getByTestId('overlap-choices')).toBeVisible();
    await expect(page.getByTestId('overlap-choices').getByRole('button')).toHaveCount(2);
    const overlapBeta = page.getByTestId('overlap-choices').getByRole('button', { name: 'Overlap Beta' });
    await overlapBeta.focus();
    await page.keyboard.press('Enter');
    expect((await page.evaluate(() => window.__stage26cFoundation!.snapshot())).selectedSystemId64).toBe(100_000_001);

    const contextExtension = await page.evaluate(() => window.__stage26cFoundation!.loseContext());
    expect(contextExtension).toBe(true);
    await expect(page.getByTestId('context-state')).toHaveText('context restored', { timeout: 10_000 });
    await canvas.click({ position: target });
    await expect(page.getByTestId('context-state')).toHaveText('context usable');

    const cameraBefore = await page.evaluate(() => window.__stage26cFoundation!.snapshot().camera);
    await canvas.hover({ position: { x: box.width / 2, y: box.height / 2 } });
    await page.mouse.wheel(0, -120);
    await expect.poll(async () => (await page.evaluate(() => window.__stage26cFoundation!.snapshot().camera.zoom)))
      .not.toBe(cameraBefore.zoom);
    await page.keyboard.down('Shift');
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2 + 40, { steps: 4 });
    await page.mouse.up();
    await page.keyboard.up('Shift');
    const cameraAfter = await page.evaluate(() => window.__stage26cFoundation!.snapshot().camera);
    expect(cameraAfter.bearingDeg).not.toBe(0);
    expect(cameraAfter.pitchDeg).not.toBe(0);

    const handoffSelect = page.getByLabel('Return from feature');
    for (const workflow of ['compare', 'savedSystems', 'evidenceMap', 'systemDetail', 'clusterSearch', 'planner', 'finder'] as const) {
      await handoffSelect.selectOption(workflow);
      await expect(page.getByTestId('return-workflow')).toHaveText(workflow);
      expect((await page.evaluate(() => window.__stage26cFoundation!.snapshot())).camera).toEqual(cameraAfter);
    }
    expect((await page.evaluate(() => window.__stage26cFoundation!.snapshot())).omittedHandoffSystemIds).toEqual([]);

    await page.getByRole('button', { name: 'Hide regions' }).click();
    await expect(page.locator('.map-foundation-labels span')).toHaveCount(0);
    await page.getByRole('button', { name: 'Request Plan hand-off' }).click();
    await expect(page.getByTestId('last-interaction')).toHaveText('navigateToPlanner');
    await expect(page.getByTestId('last-host-command')).toHaveText('openPlanner');
    await expect(page.getByText('No plan mutation occurred.')).toBeVisible();
    expect(consoleErrors).toEqual([]);
  });
}
