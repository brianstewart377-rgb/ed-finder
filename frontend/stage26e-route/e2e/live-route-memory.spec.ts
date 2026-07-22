import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Browser, type BrowserContext, type Page } from '@playwright/test';

const VIEWPORTS = [
  { width: 1280, height: 720 },
  { width: 1440, height: 900 },
] as const;

type RouteMeasurement = {
  viewport: { width: number; height: number };
  finderResponseStatus: number;
  heatmapResponseStatus: number;
  clusterResponseStatus: number;
  timelineResponseStatus: number;
  axeViolationCount: number;
  beforeOverlays: Awaited<ReturnType<typeof measureHeap>>;
  afterOverlays: Awaited<ReturnType<typeof measureHeap>>;
  snapshot: Record<string, unknown>;
  requestedApiPaths: string[];
};

const LIVE_ROUTE_HEAP_BUDGET_BYTES = 256 * 1_048_576;

async function measureHeap(context: BrowserContext, page: Page) {
  await page.waitForTimeout(1_000);
  const session = await context.newCDPSession(page);
  const samplesBytes: number[] = [];
  try {
    await session.send('Performance.enable');
    for (let index = 0; index < 7; index += 1) {
      const result = await session.send('Performance.getMetrics');
      const sample = result.metrics.find((metric) => metric.name === 'JSHeapUsedSize')?.value ?? null;
      if (sample == null) break;
      samplesBytes.push(sample);
      await page.waitForTimeout(100);
    }
  } finally {
    await session.detach();
  }
  const supported = samplesBytes.length === 7;
  const minBytes = supported ? Math.min(...samplesBytes) : null;
  const maxBytes = supported ? Math.max(...samplesBytes) : null;
  return {
    supported,
    budgetBytes: LIVE_ROUTE_HEAP_BUDGET_BYTES,
    sampleCount: samplesBytes.length,
    samplesBytes,
    minBytes,
    maxBytes,
    spreadBytes: minBytes != null && maxBytes != null ? maxBytes - minBytes : null,
    withinBudget: maxBytes == null ? null : maxBytes <= LIVE_ROUTE_HEAP_BUDGET_BYTES,
  };
}

async function measureViewport(browser: Browser, viewport: typeof VIEWPORTS[number]): Promise<RouteMeasurement> {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const requestedApiPaths: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname === '/api/local/search' || url.pathname.startsWith('/api/map/')) {
      requestedApiPaths.push(`${url.pathname}${url.search}`);
    }
  });
  try {
    let finderResponseStatus = 0;
    let finderSystemCount = 0;
    await test.step('load 500 live Finder systems', async () => {
      await page.goto('/#finder', { waitUntil: 'domcontentloaded' });
      await page.getByLabel('Results per page').fill('500');
      const finderResponsePromise = page.waitForResponse((response) => (
        new URL(response.url()).pathname === '/api/local/search'
      ));
      await page.getByTestId('search-submit').click();
      const finderResponse = await finderResponsePromise;
      finderResponseStatus = finderResponse.status();
      const finderBody = await finderResponse.json() as { results?: unknown[] };
      finderSystemCount = finderBody.results?.length ?? 0;
      expect(finderResponseStatus).toBe(200);
      expect(finderSystemCount).toBe(500);
      await expect(page.getByTestId('search-summary')).toBeVisible();
    });

    await test.step('mount the flagged production route candidate', async () => {
      await page.getByTestId('nav-map').click();
      await expect(page.getByTestId('stage26e-production-map')).toBeVisible();
      await expect(page.getByTestId('stage26e-production-map-viewport')).toBeVisible();
      await expect.poll(async () => page.evaluate(() => window.__stage26eProductionMap?.snapshot().finderSystemCount ?? 0))
        .toBe(500);
    });

    let beforeOverlays!: Awaited<ReturnType<typeof measureHeap>>;
    await test.step('sample precise heap before aggregate overlays', async () => {
      beforeOverlays = await measureHeap(context, page);
      expect(beforeOverlays.supported).toBe(true);
    });

    let heatmapResponseStatus = 0;
    let clusterResponseStatus = 0;
    let timelineResponseStatus = 0;
    let heatmapCellCount = 0;
    let heatmapSourceTruncated = false;
    let aggregateHullCount = 0;
    let timelinePointCount = 0;
    await test.step('load and compose live aggregate overlays', async () => {
      const aggregateUrls = {
        heatmap: 'http://127.0.0.1:4174/api/map/heatmap?max_cells=50000',
        clusters: 'http://127.0.0.1:4174/api/map/clusters/hulls?max_hulls=2000',
        timeline: 'http://127.0.0.1:4174/api/map/timeline?bucket=month',
      };
      const [heatmapSource, clusterSource, timelineSource] = await Promise.all([
        context.request.get(aggregateUrls.heatmap),
        context.request.get(aggregateUrls.clusters),
        context.request.get(aggregateUrls.timeline),
      ]);
      expect(heatmapSource.status()).toBe(200);
      expect(clusterSource.status()).toBe(200);
      expect(timelineSource.status()).toBe(200);
      const [heatmapText, clusterText, timelineText] = await Promise.all([
        heatmapSource.text(),
        clusterSource.text(),
        timelineSource.text(),
      ]);
      const heatmapBody = JSON.parse(heatmapText) as { cells?: unknown[]; truncated?: boolean };
      const clusterBody = JSON.parse(clusterText) as { clusters?: unknown[] };
      const timelineBody = JSON.parse(timelineText) as { points?: unknown[] };
      heatmapCellCount = Math.min(50_000, heatmapBody.cells?.length ?? 0);
      heatmapSourceTruncated = heatmapBody.truncated ?? false;
      aggregateHullCount = Math.min(2_000, clusterBody.clusters?.length ?? 0);
      timelinePointCount = Math.min(1_200, timelineBody.points?.length ?? 0);
      await page.route('**/api/map/heatmap?**', (route) => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: heatmapText,
      }));
      await page.route('**/api/map/clusters/hulls?**', (route) => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: clusterText,
      }));
      await page.route('**/api/map/timeline?**', (route) => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: timelineText,
      }));
      const heatmapResponsePromise = page.waitForResponse((response) => (
        new URL(response.url()).pathname === '/api/map/heatmap'
      ));
      const clusterResponsePromise = page.waitForResponse((response) => (
        new URL(response.url()).pathname === '/api/map/clusters/hulls'
      ));
      const timelineResponsePromise = page.waitForResponse((response) => (
        new URL(response.url()).pathname === '/api/map/timeline'
      ));
      await page.getByTestId('stage26e-map-heatmap-toggle').click();
      await page.getByTestId('stage26e-map-clusters-toggle').click();
      await page.getByTestId('stage26e-map-timeline-toggle').click();
      const [heatmapResponse, clusterResponse, timelineResponse] = await Promise.all([
        heatmapResponsePromise,
        clusterResponsePromise,
        timelineResponsePromise,
      ]);
      heatmapResponseStatus = heatmapResponse.status();
      clusterResponseStatus = clusterResponse.status();
      timelineResponseStatus = timelineResponse.status();
      expect(heatmapResponseStatus).toBe(200);
      expect(clusterResponseStatus).toBe(200);
      expect(timelineResponseStatus).toBe(200);
      expect(heatmapCellCount).toBeGreaterThan(0);
      expect(aggregateHullCount).toBeGreaterThan(0);
      expect(timelinePointCount).toBeGreaterThan(0);
      await page.waitForTimeout(5_000);
    });

    let afterOverlays!: Awaited<ReturnType<typeof measureHeap>>;
    let snapshot!: RouteMeasurement['snapshot'];
    let axeViolationCount = -1;
    await test.step('check the composed route accessibility surface', async () => {
      const accessibility = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();
      axeViolationCount = accessibility.violations.length;
      expect(accessibility.violations).toEqual([]);
    });
    await test.step('sample and assert the composed live-route heap', async () => {
      afterOverlays = await measureHeap(context, page);
      const estimatedOverlayBufferBytes = heatmapCellCount * 24 + aggregateHullCount * 1_536;
      snapshot = {
        renderer: 'r3f',
        routeFlagEnabled: true,
        surfaceKind: 'ready',
        finderSystemCount,
        finderResponseTruncated: false,
        heatmapCellCount,
        heatmapSourceTruncated,
        aggregateHullCount,
        timelinePointCount,
        estimatedOverlayBufferBytes,
        overlayBufferWithinBudget: estimatedOverlayBufferBytes <= 8 * 1_048_576,
        regionGeometryExposed: false,
        heapBudgetBytes: LIVE_ROUTE_HEAP_BUDGET_BYTES,
      };
      expect(afterOverlays.supported).toBe(true);
      expect(afterOverlays.withinBudget).toBe(true);
      expect(snapshot.overlayBufferWithinBudget).toBe(true);
      expect(snapshot.regionGeometryExposed).toBe(false);
      expect(requestedApiPaths.some((apiPath) => apiPath.startsWith('/api/map/regions'))).toBe(false);
    });

    return {
      viewport,
      finderResponseStatus,
      heatmapResponseStatus,
      clusterResponseStatus,
      timelineResponseStatus,
      axeViolationCount,
      beforeOverlays,
      afterOverlays,
      snapshot,
      requestedApiPaths,
    };
  } finally {
    await context.close();
  }
}

const measurements: RouteMeasurement[] = [];

for (const viewport of VIEWPORTS) {
  test(`measures the default-off candidate at ${viewport.width}x${viewport.height}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const measurement = await measureViewport(browser, viewport);
    measurements.push(measurement);
    await test.info().attach(`stage-26e-live-route-memory-${viewport.width}x${viewport.height}`, {
      body: JSON.stringify(measurement, null, 2),
      contentType: 'application/json',
    });
  });
}

test.afterAll(async () => {
  const evidence = {
    schema_version: 1,
    stage: '26E',
    recorded_on: '2026-07-22',
    route: '#map',
    renderer: 'r3f',
    activation: 'measurement build only; normal production flag remains unset',
    data_source: 'live ED-Finder API payloads fetched through the Vite preview proxy and fulfilled unchanged into the measured route',
    collection_method: 'Chromium CDP Performance.getMetrics JSHeapUsedSize after a one-second idle; garbage collection not forced',
    accessibility_standard: 'WCAG 2 A/AA and WCAG 2.1 A/AA detectable rules',
    region_geometry_exposed: false,
    budget_bytes: measurements[0]?.afterOverlays.budgetBytes ?? null,
    measurements,
    status: measurements.length === VIEWPORTS.length
      && measurements.every((entry) => (
        entry.afterOverlays.withinBudget && entry.axeViolationCount === 0
      ))
      ? 'pass'
      : 'incomplete_or_failed',
  };
  if (process.env.STAGE26E_CAPTURE === '1') {
    const outputDirectory = path.resolve(process.cwd(), '../artifacts/map-foundation/stage-26e');
    await mkdir(outputDirectory, { recursive: true });
    await writeFile(
      path.join(outputDirectory, 'live-route-memory.json'),
      `${JSON.stringify(evidence, null, 2)}\n`,
      'utf8',
    );
  }
});
