import { expect, test } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

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
    expect(initial.productionHeatmapCellCount).toBe(16);
    expect(initial.productionAggregateHullCount).toBe(3);
    expect(initial.productionTimelinePointCount).toBe(3);
    expect(initial.productionSurfaceKind).toBe('ready');
    expect(initial.estimatedOverlayBufferBytes).toBeGreaterThan(0);

    const overlapBeta = page
      .getByRole('complementary', { name: 'Map keyboard companion' })
      .getByRole('button', { name: 'Overlap Beta' });
    await overlapBeta.click();
    expect((await page.evaluate(() => window.__stage26cFoundation!.snapshot())).selectedSystemId64).toBe(100_000_001);

    const cameraBefore = await page.evaluate(() => window.__stage26cFoundation!.snapshot().camera);
    const contextExtension = await page.evaluate(() => window.__stage26cFoundation!.loseContext());
    expect(contextExtension).toBe(true);
    await expect(page.getByTestId('context-state')).toHaveText('context restored', { timeout: 10_000 });
    await overlapBeta.click();
    await expect(page.getByTestId('context-state')).toHaveText('context usable');

    const handoffSelect = page.getByLabel('Return from feature');
    for (const workflow of ['compare', 'savedSystems', 'evidenceMap', 'systemDetail', 'clusterSearch', 'planner', 'finder'] as const) {
      await handoffSelect.selectOption(workflow);
      await expect(page.getByTestId('return-workflow')).toHaveText(workflow);
      expect((await page.evaluate(() => window.__stage26cFoundation!.snapshot())).camera).toEqual(cameraBefore);
    }
    expect((await page.evaluate(() => window.__stage26cFoundation!.snapshot())).omittedHandoffSystemIds).toEqual([]);

    await page.getByRole('button', { name: 'Hide regions' }).click();
    await expect(page.locator('.map-foundation-labels span')).toHaveCount(0);
    await page.getByRole('button', { name: 'Request Plan hand-off' }).click();
    await expect(page.getByTestId('last-interaction')).toHaveText('navigateToPlanner');
    await expect(page.getByTestId('last-host-command')).toHaveText('openPlanner');
    await expect(page.getByText('No plan mutation occurred.')).toBeVisible();

    const viewPreset = page.getByLabel('View preset');
    for (const preset of ['galaxy', 'reference', 'results'] as const) {
      await viewPreset.selectOption(preset);
      await expect.poll(async () => (
        await page.evaluate(() => window.__stage26cFoundation?.snapshot().productionViewPreset ?? null)
      )).toBe(preset);
    }

    const companion = page.getByRole('complementary', { name: 'Map keyboard companion' });
    await expect(companion.getByRole('heading', { name: 'Context companion' })).toBeVisible();
    const unnamedControls = await page.locator('button:not([disabled]), select:not([disabled])').evaluateAll((controls) =>
      controls.filter((control) => !(control.getAttribute('aria-label') || control.textContent?.trim())).length,
    );
    expect(unnamedControls).toBe(0);

    const performance = await page.evaluate(() => window.__stage26cFoundation!.measurePerformance());
    expect(performance.frameSampleCount).toBe(60);
    expect(performance.frameP95Ms).toBeLessThan(50);
    expect(performance.frameMaxMs).toBeLessThan(100);
    if (performance.gpuTimerSupported) expect(performance.gpuProbeMs).not.toBeNull();
    const gpuTiming = await page.evaluate(() => window.__stage26cFoundation!.measureGpuTiming(3));
    expect(gpuTiming.requestedSampleCount).toBe(3);
    if (gpuTiming.timerSupported) {
      expect(gpuTiming.validSampleCount).toBeGreaterThan(0);
      expect(gpuTiming.p95Ms).not.toBeNull();
    }
    await test.info().attach('stage-26e-performance', {
      body: JSON.stringify(performance, null, 2),
      contentType: 'application/json',
    });
    if (process.env.STAGE26E_CAPTURE === '1') {
      const outputDirectory = path.resolve(process.cwd(), '../artifacts/map-foundation/stage-26e');
      await mkdir(outputDirectory, { recursive: true });
      await writeFile(
        path.join(outputDirectory, `performance-${viewport.width}x${viewport.height}.json`),
        `${JSON.stringify({ viewport, browser: 'chromium', measurement: performance }, null, 2)}\n`,
        'utf8',
      );
    }
    expect(consoleErrors).toEqual([]);
  });
}
