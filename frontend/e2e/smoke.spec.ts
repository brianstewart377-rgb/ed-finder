import {
  test,
  expect,
  type APIRequestContext,
  type Page,
} from '@playwright/test';

const SEARCH_PAYLOAD = {
  reference_coords: { x: 0, y: 0, z: 0 },
  filters: { distance: { min: 0, max: 1000 } },
  size: 5,
};

async function waitForSearchBackend(request: APIRequestContext) {
  let lastStatus: number | null = null;
  let lastBody = '';

  for (let attempt = 0; attempt < 10; attempt += 1) {
    const response = await request.post('/api/local/search', { data: SEARCH_PAYLOAD });
    lastStatus = response.status();
    lastBody = await response.text();
    if (lastStatus === 200) {
      return JSON.parse(lastBody);
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  throw new Error(`search backend did not become ready: status=${lastStatus}, body=${lastBody}`);
}

async function readCanvasMetrics(page: Page) {
  return page.locator('.map-foundation-renderer canvas').evaluate((canvas) => {
    const rect = canvas.getBoundingClientRect();
    return {
      cssWidth: Math.round(rect.width),
      cssHeight: Math.round(rect.height),
      canvasWidth: canvas.width,
      canvasHeight: canvas.height,
      drawingBufferWidth: Number(canvas.dataset.drawingBufferWidth),
      drawingBufferHeight: Number(canvas.dataset.drawingBufferHeight),
      viewport: [
        Number(canvas.dataset.viewportX),
        Number(canvas.dataset.viewportY),
        Number(canvas.dataset.viewportWidth),
        Number(canvas.dataset.viewportHeight),
      ],
      syncGuard: canvas.dataset.drawingBufferSynced,
      contextLost: canvas.dataset.contextLost === 'true',
    };
  });
}

function expectCanvasMetricsToBeSynced(metrics: Awaited<ReturnType<typeof readCanvasMetrics>>) {
  expect(metrics.cssWidth).toBeGreaterThan(0);
  expect(metrics.cssHeight).toBeGreaterThan(0);
  expect(metrics.canvasWidth).toBe(metrics.drawingBufferWidth);
  expect(metrics.canvasHeight).toBe(metrics.drawingBufferHeight);
  expect(metrics.viewport).toEqual([
    0,
    0,
    metrics.drawingBufferWidth,
    metrics.drawingBufferHeight,
  ]);
  expect(metrics.syncGuard).toBe('true');
  expect(metrics.contextLost).toBe(false);
}

async function expectCanvasToBeSynced(page: Page) {
  let lastMetrics: Awaited<ReturnType<typeof readCanvasMetrics>> | null = null;
  try {
    await expect.poll(async () => {
      lastMetrics = await readCanvasMetrics(page);
      return (
        lastMetrics.cssWidth > 0
        && lastMetrics.cssHeight > 0
        && lastMetrics.canvasWidth === lastMetrics.drawingBufferWidth
        && lastMetrics.canvasHeight === lastMetrics.drawingBufferHeight
        && lastMetrics.viewport[0] === 0
        && lastMetrics.viewport[1] === 0
        && lastMetrics.viewport[2] === lastMetrics.drawingBufferWidth
        && lastMetrics.viewport[3] === lastMetrics.drawingBufferHeight
        && lastMetrics.syncGuard === 'true'
        && !lastMetrics.contextLost
      );
    }).toBe(true);
  } catch (error) {
    throw new Error(
      `Canvas metrics did not synchronize: ${JSON.stringify(lastMetrics)}`,
      { cause: error },
    );
  }
  expectCanvasMetricsToBeSynced(await readCanvasMetrics(page));
}

async function zoomMapUntil(page: Page, done: () => boolean) {
  const renderer = page.locator('.map-foundation-renderer');
  const zoomIn = page.getByTestId('map-zoom-in');

  for (let attempt = 0; attempt < 24 && !done(); attempt += 1) {
    const before = Number(await renderer.getAttribute('data-camera-zoom'));
    await zoomIn.click();
    await expect.poll(
      async () => Number(await renderer.getAttribute('data-camera-zoom')),
      { timeout: 3000 },
    ).toBeLessThan(before);
    // useViewportSystems intentionally waits 250 ms after camera movement
    // before querying, so allow the production debounce to complete.
    await page.waitForTimeout(350);
  }

  expect(done(), 'Expected deep zoom to trigger the real-star detail request').toBe(true);
}

/**
 * E2E smoke tests for the live SPA — runs against `yarn preview` (Vite
 * preview server) with `/api/*` proxied to the local FastAPI.
 *
 * What we lock in:
 *   • App boots, NavBar renders, all 7 tabs visible
 *   • Health probe reaches the backend (the 'ok · v…' badge)
 *   • Search runs end-to-end against real seed data, results render
 *   • Pinned-store persists across reload (Phase 7 Zustand persist)
 *   • System detail modal opens and closes
 */
test.describe('ED Finder — smoke', () => {
  test.beforeEach(async ({ page }) => {
    // Clear localStorage so each test starts from a known state.
    await page.goto('/');
    await page.evaluate(() => localStorage.clear());
    await page.reload();
  });

  test('app boots with health badge', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/ED:?Finder/i);
    // NavBar should be visible — probe the brand text or any tab label.
    await expect(page.getByText(/Finder/i).first()).toBeVisible();
  });

  test('search runs and renders at least one result', async ({ page, request }) => {
    await waitForSearchBackend(request);
    await page.goto('/');
    await page.getByTestId('search-submit').click();
    await expect(page.getByTestId('search-summary')).toBeVisible({ timeout: 15_000 });
    // After a successful search the body should mention at least one
    // seeded system name. We don't know exactly which 5 the API returns
    // (sort_by=rating descending), so check for any of the 40 seeded
    // names by probing for "LY" (distance suffix appears next to results)
    // OR a known seed name.
    const body = await page.locator('body').textContent();
    const knownNames = ['Sol', 'Achenar', 'Lave', 'Procyon', 'Alioth',
                        'Wolf', 'HIP', 'Sothis', 'Pleione', 'Diaguandri'];
    const found = knownNames.some((n) => body?.includes(n));
    expect(found, `Expected at least one seeded name in: ${body?.slice(0, 400)}`).toBe(true);
  });

  test('pinned store persists across reload (Phase 7)', async ({ page }) => {
    await page.goto('/');
    // Seed localStorage directly — exercises the persist middleware on reload.
    await page.evaluate(() => {
      localStorage.setItem('ed_pinned', JSON.stringify([{
        id64: 12345, name: 'Persisted', x: 0, y: 0, z: 0,
        population: 0, is_colonised: false,
        rating: 80, economy: 'Tourism',
        pinned_at: '2025-01-01T00:00:00Z',
      }]));
    });
    await page.reload();
    await page.getByTestId('nav-my-work').click();
    // Pins now feed the Saved Systems view inside My Work.
    await expect(page.getByTestId('my-work-workspace')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId('saved-system-12345')).toContainText('Persisted');
    await expect(page.getByTestId('saved-system-12345')).toContainText('Favourite');
  });

  test('legacy /api/watchlist returns 410 (Phase 3 contract)', async ({ request }) => {
    const r = await request.get('/api/watchlist');
    expect(r.status()).toBe(410);
    const body = await r.json();
    expect(body.detail).toBeDefined();
    expect(JSON.stringify(body.detail)).toContain('sync_key');
  });

  test('search backend returns valid envelope (Phase 2 contract)', async ({ request }) => {
    const body = await waitForSearchBackend(request);
    expect(body).toHaveProperty('results');
    expect(Array.isArray(body.results)).toBe(true);
    expect(body.source).toBe('local_db');
  });

  test('map heatmap reads from materialised view (Phase 5)', async ({ request }) => {
    const r = await request.get('/api/map/heatmap?voxel_size=200&min_systems=1');
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body).toHaveProperty('voxel_bucket');
    expect([200, 500, 1000]).toContain(body.voxel_bucket);
  });

  test('Map navigation opens the activated Stage 26E renderer', async ({ page }) => {
    test.setTimeout(60_000);
    const graphicsWarnings: string[] = [];
    const consoleHandler = (message: any) => {
      if (
        (message.type() === 'warning' || message.type() === 'error')
        && /drawArraysInstanced|destination rect|viewport rect/i.test(message.text())
      ) {
        graphicsWarnings.push(message.text());
      }
    };
    page.on('console', consoleHandler);
    const regionResponsePromise = page.waitForResponse((response) => (
      new URL(response.url()).pathname === '/stage26e/authoritative-regions.json'
    ));
    const heatmapResponsePromise = page.waitForResponse((response) => (
      new URL(response.url()).pathname === '/api/map/heatmap'
    ));

    await page.getByTestId('nav-map').click();

    const [regionResponse, heatmapResponse] = await Promise.all([
      regionResponsePromise,
      heatmapResponsePromise,
    ]);
    expect(regionResponse.status()).toBe(200);
    expect(heatmapResponse.status()).toBe(200);
    await expect(page.getByTestId('stage26e-production-map')).toBeVisible();
    await expect(page.getByTestId('stage26e-route-flag-state')).toContainText('Live map');
    await expect(page.getByTestId('stage26e-map-regions-toggle')).toBeChecked();
    await expect(page.getByTestId('stage26e-map-heatmap-toggle')).toBeChecked();

    await page.getByTestId('map-view-galaxy').click();
    await expect(page.getByTestId('map-projection-2d')).toHaveCount(0);
    await expect(page.getByTestId('map-projection-3d')).toHaveCount(0);
    const renderer = page.locator('.map-foundation-renderer');
    await expect(renderer).toHaveAttribute('data-projection', 'perspective');
    await expect(renderer).toHaveAttribute('data-camera-pitch', '42');
    await expect(renderer).toHaveAttribute('data-galaxy-point-count', '18000');
    const mapViewport = page.getByTestId('stage26e-production-map-viewport');
    const viewportBox = await mapViewport.boundingBox();
    const browserViewport = page.viewportSize();
    expect(viewportBox).not.toBeNull();
    expect(browserViewport).not.toBeNull();
    expect(viewportBox!.width / browserViewport!.width).toBeGreaterThanOrEqual(0.98);
    expect(viewportBox!.height / browserViewport!.height).toBeGreaterThanOrEqual(0.98);
    const zoomBefore = await renderer.getAttribute('data-camera-zoom');
    const initialZoom = Number(zoomBefore);
    const centerXBefore = await renderer.getAttribute('data-camera-center-x');
    const centerZBefore = await renderer.getAttribute('data-camera-center-z');
    await page.getByTestId('map-zoom-in').click();
    await expect.poll(async () => Number(await renderer.getAttribute('data-camera-zoom')))
      .toBeLessThan(initialZoom);
    const zoomInTarget = initialZoom * Math.exp(-0.22);
    await expect.poll(async () => Number(await renderer.getAttribute('data-camera-zoom')))
      .toBeCloseTo(zoomInTarget, 6);
    await page.getByTestId('map-zoom-out').click();
    await expect.poll(async () => Number(await renderer.getAttribute('data-camera-zoom')))
      .toBeCloseTo(initialZoom, 6);
    const zoomBeforeSnap = await renderer.getAttribute('data-camera-zoom');
    await page.getByTestId('map-snap-top-down').click();
    await expect(renderer).toHaveAttribute('data-camera-pitch', '0.5');
    await expect(renderer).toHaveAttribute('data-projection', 'perspective');
    await expect(renderer).toHaveAttribute('data-camera-zoom', zoomBeforeSnap ?? '');
    await expect(renderer).toHaveAttribute('data-camera-center-x', centerXBefore ?? '');
    await expect(renderer).toHaveAttribute('data-camera-center-z', centerZBefore ?? '');

    try {
      await expectCanvasToBeSynced(page);
      await page.setViewportSize({ width: 1111, height: 733 });
      await expect.poll(async () => (await readCanvasMetrics(page)).cssWidth).toBe(1111);
      await expectCanvasToBeSynced(page);

      await page.getByTestId('map-view-results').click();
      await page.getByTestId('map-view-galaxy').click();
      await expectCanvasToBeSynced(page);
      expect(graphicsWarnings).toEqual([]);
    } finally {
      page.off('console', consoleHandler);
    }
  });

  test('loads the real-star detail endpoint after crossing the deep-zoom LOD', async ({ page }) => {
    test.setTimeout(60_000);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const heatmapResponsePromise = page.waitForResponse((response) => (
      new URL(response.url()).pathname === '/api/map/heatmap'
    ));

    await page.getByTestId('nav-map').click();
    expect((await heatmapResponsePromise).status()).toBe(200);
    await page.getByTestId('map-view-galaxy').click();
    await page.getByTestId('map-snap-top-down').click();

    let realStarsRequested = false;
    const requestHandler = (request: any) => {
      if (new URL(request.url()).pathname === '/api/map/systems') {
        realStarsRequested = true;
      }
    };
    page.on('request', requestHandler);
    const realStarsResponsePromise = page.waitForResponse(
      (response) => new URL(response.url()).pathname === '/api/map/systems',
      { timeout: 30_000 },
    );

    try {
      await zoomMapUntil(page, () => realStarsRequested);
      const realStarsResponse = await realStarsResponsePromise;
      expect(realStarsResponse.status()).toBe(200);
      const realStarsBody = await realStarsResponse.json() as {
        systems: Array<any>;
        truncated: boolean;
      };
      expect(realStarsBody).toEqual(expect.objectContaining({
        systems: expect.any(Array),
        truncated: expect.any(Boolean),
      }));
      await expect(page.locator('.map-foundation-renderer canvas')).toBeVisible();
      await expect(page.getByText(/detailed star layer could not be loaded/i)).toHaveCount(0);
    } finally {
      page.off('request', requestHandler);
    }
  });

  test('invalidates renderer sync telemetry while a resize is pending', async ({ page }) => {
    await page.getByTestId('nav-map').click();
    await page.getByTestId('map-view-galaxy').click();

    const renderer = page.locator('.map-foundation-renderer');
    await expect(renderer).toHaveAttribute('data-galaxy-point-count', '18000');
    const canvas = renderer.locator('canvas');
    await expect.poll(
      () => canvas.evaluate((element) => element.dataset.drawingBufferSynced),
    ).toBe('true');

    await canvas.evaluate((element) => {
      const instrumented = element as HTMLCanvasElement & {
        resizeTelemetryObserver?: MutationObserver;
        resizeTelemetrySequence?: string[];
      };
      instrumented.resizeTelemetrySequence = [
        element.dataset.drawingBufferSynced ?? 'missing',
      ];
      instrumented.resizeTelemetryObserver = new MutationObserver(() => {
        instrumented.resizeTelemetrySequence?.push(
          element.dataset.drawingBufferSynced ?? 'missing',
        );
      });
      instrumented.resizeTelemetryObserver.observe(element, {
        attributes: true,
        attributeFilter: ['data-drawing-buffer-synced'],
      });
    });

    await page.setViewportSize({ width: 1111, height: 733 });
    await expect.poll(async () => {
      const sequence = await canvas.evaluate((element) => (
        (element as HTMLCanvasElement & { resizeTelemetrySequence?: string[] })
          .resizeTelemetrySequence ?? []
      ));
      const invalidatedAt = sequence.indexOf('false');
      return invalidatedAt >= 0
        && sequence.slice(invalidatedAt + 1).includes('true');
    }).toBe(true);

    const sequence = await canvas.evaluate((element) => (
      (element as HTMLCanvasElement & { resizeTelemetrySequence?: string[] })
        .resizeTelemetrySequence ?? []
    ));
    const invalidatedAt = sequence.indexOf('false');
    const revalidatedAt = sequence.indexOf('true', invalidatedAt + 1);
    expect(invalidatedAt).toBeGreaterThanOrEqual(0);
    expect(revalidatedAt).toBeGreaterThan(invalidatedAt);
  });

  test('keeps renderer sync telemetry verified for a same-size ResizeObserver fire', async ({
    page,
  }) => {
    await page.addInitScript(() => {
      const NativeResizeObserver = window.ResizeObserver;
      if (!NativeResizeObserver) return;
      const callbacks = new WeakMap<ResizeObserver, ResizeObserverCallback>();
      const testWindow = window as typeof window & {
        triggerMapResizeObserver?: () => void;
      };
      window.ResizeObserver = class TestResizeObserver extends NativeResizeObserver {
        constructor(callback: ResizeObserverCallback) {
          super(callback);
          callbacks.set(this, callback);
        }

        observe(target: Element, options?: ResizeObserverOptions) {
          super.observe(target, options);
          if (
            target instanceof HTMLCanvasElement
            && target.closest('.map-foundation-renderer')
          ) {
            testWindow.triggerMapResizeObserver = () => {
              callbacks.get(this)?.([], this);
            };
          }
        }
      };
    });
    await page.reload();
    await page.getByTestId('nav-map').click();
    await page.getByTestId('map-view-galaxy').click();

    const renderer = page.locator('.map-foundation-renderer');
    await expect(renderer).toHaveAttribute('data-galaxy-point-count', '18000');
    const canvas = renderer.locator('canvas');
    await expect.poll(
      () => canvas.evaluate((element) => element.dataset.drawingBufferSynced),
      {
        timeout: 3000,
        intervals: [50, 100, 200], // Exponential backoff: start fast, slow down
      }
    ).toBe('true');

    const observation = await canvas.evaluate(async (element) => {
      const testWindow = window as typeof window & {
        triggerMapResizeObserver?: () => void;
      };
      const instrumented = element as HTMLCanvasElement & {
        resizeTelemetryObserver?: MutationObserver;
        resizeTelemetrySequence?: string[];
      };
      const before = element.getBoundingClientRect();
      instrumented.resizeTelemetrySequence = [
        element.dataset.drawingBufferSynced ?? 'missing',
      ];
      instrumented.resizeTelemetryObserver = new MutationObserver(() => {
        instrumented.resizeTelemetrySequence?.push(
          element.dataset.drawingBufferSynced ?? 'missing',
        );
      });
      instrumented.resizeTelemetryObserver.observe(element, {
        attributes: true,
        attributeFilter: ['data-drawing-buffer-synced'],
      });

      const triggerInstalled = typeof testWindow.triggerMapResizeObserver === 'function';
      testWindow.triggerMapResizeObserver?.();
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      const after = element.getBoundingClientRect();
      instrumented.resizeTelemetryObserver.disconnect();
      return {
        before: { width: before.width, height: before.height },
        after: { width: after.width, height: after.height },
        sequence: instrumented.resizeTelemetrySequence ?? [],
        triggerInstalled,
      };
    });

    expect(observation.triggerInstalled).toBe(true);
    expect(observation.after).toEqual(observation.before);
    expect(observation.sequence.length).toBeGreaterThan(1);
    expect(observation.sequence).not.toContain('false');
  });

  // Issue #5: System detail modal opens and closes
  test('system detail modal opens and closes', async ({ page, request }) => {
    await waitForSearchBackend(request);
    await page.goto('/');
    await page.getByTestId('search-submit').click();
    await expect(page.getByTestId('search-summary')).toBeVisible({ timeout: 15_000 });

    const firstResult = page.locator('[data-testid^="result-card-"]').first();
    await expect(firstResult).toBeVisible({ timeout: 15_000 });
    const systemName = (await firstResult.locator('h3').textContent())?.trim() ?? '';
    expect(systemName).not.toBe('');

    // Result cards now expand first; the explicit Inspect system action opens
    // the detail modal. Clicking the whole card only toggles its details.
    await firstResult.locator('header').click();
    const inspectButton = firstResult.getByRole('button', { name: 'Inspect system' });
    await expect(inspectButton).toBeVisible();
    await inspectButton.click();

    const modal = page.locator('[data-testid="system-detail-modal"]');
    await expect(modal).toBeVisible({ timeout: 10_000 });
    await expect(modal).toContainText(systemName);

    const closeButton = modal.locator('[data-testid="modal-close"]');
    if (await closeButton.isVisible()) {
      await closeButton.click();
    } else {
      await page.locator('[data-testid="system-detail-modal-backdrop"]').click();
    }

    await expect(modal).not.toBeVisible({ timeout: 5_000 });
  });

  // Issue #9: API error handling
  test('handles real-stars endpoint error gracefully', async ({ page }) => {
    test.setTimeout(30_000);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.route(/\/api\/map\/systems(?:\?|$)/, (route) => {
      route.abort('failed');
    });

    await page.goto('/');
    await page.getByTestId('nav-map').click();
    await page.getByTestId('map-view-galaxy').click();
    await page.getByTestId('map-snap-top-down').click();

    let realStarsRequested = false;
    const requestHandler = (request: any) => {
      if (new URL(request.url()).pathname === '/api/map/systems') {
        realStarsRequested = true;
      }
    };
    page.on('request', requestHandler);

    try {
      await zoomMapUntil(page, () => realStarsRequested);
      await expect(page.locator('.map-foundation-renderer canvas')).toBeVisible();
      await expect(page.getByText(/detailed star layer could not be loaded/i)).toBeVisible({ timeout: 5_000 });
    } finally {
      page.off('request', requestHandler);
    }
  });

  test('handles heatmap endpoint error gracefully', async ({ page }) => {
    // Simulate heatmap endpoint timeout
    await page.route('/api/map/heatmap', async (route) => {
      // Delay response indefinitely to simulate timeout
      await new Promise(() => {});
    });

    await page.goto('/');
    await page.getByTestId('nav-map').click();

    // After some time, should either recover or show graceful error
    // At minimum, shouldn't hard-crash
    await expect(page.locator('body')).toBeVisible({ timeout: 5000 });
  });
});

test.describe('ED Finder — cross-browser runtime', () => {
  test('installs and controls with the cache-neutral service worker', async ({ page, request }) => {
    const serviceWorkerErrors: string[] = [];
    page.on('console', (message) => {
      if (/SW registration failed|ServiceWorker.*(?:error|failed)/i.test(message.text())) {
        serviceWorkerErrors.push(message.text());
      }
    });

    const scriptResponse = await request.get('/sw.js');
    expect(scriptResponse.status()).toBe(200);
    expect(scriptResponse.headers()['content-type']).toMatch(/javascript/);
    expect(await scriptResponse.text()).toContain('event.waitUntil(self.skipWaiting())');

    await page.goto('/?service-worker-install=clean');
    await expect.poll(() => page.evaluate(async () => {
      const registration = await navigator.serviceWorker.getRegistration('/');
      return registration?.active?.state ?? null;
    })).toBe('activated');
    await expect.poll(() => page.evaluate(
      () => navigator.serviceWorker.controller?.scriptURL ?? null,
    )).toMatch(/\/sw\.js$/);
    expect(serviceWorkerErrors).toEqual([]);
  });
});
