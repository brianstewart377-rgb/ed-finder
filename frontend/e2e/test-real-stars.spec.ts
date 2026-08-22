import { test, expect, type ConsoleMessage, type Response } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  // Clear state between tests (issue #10: test isolation)
  await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({
    status: 200,
    contentType: 'text/css',
    body: '',
  }));
  await page.goto('/');
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
});

test('real-star layer renders when zoomed in', async ({ page }) => {
  test.setTimeout(120_000);
  await page.emulateMedia({ reducedMotion: 'reduce' });

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║         REAL-STAR LAYER ZOOM DETECTION TEST               ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  // Capture console logs and API calls
  const viewportMessages: string[] = [];
  const apiCalls: string[] = [];

  const consoleHandler = (msg: ConsoleMessage) => {
    const text = msg.text();
    if (text.includes('[viewport-systems]')) {
      viewportMessages.push(text);
      console.log(`[VIEWPORT] ${text}`);
    }
  };
  page.on('console', consoleHandler);

  // Intercept API calls to detect /map/systems requests
  const responseHandler = (response: Response) => {
    if (response.url().includes('/api/map/systems')) {
      const status = response.status();
      apiCalls.push(`${response.url()} → ${status}`);
      console.log(`[API] GET /map/systems → ${status}`);
    }
  };
  page.on('response', responseHandler);

  try {
    // Navigate to map with setup steps matching the passing smoke test
    console.log('Navigating to map...');
    await page.goto('/#map');
    await page.waitForLoadState('networkidle');

    // Set up the view (matching smoke.spec.ts setup) - remove error suppression (issue #2)
    console.log('Setting up map view...');
    await expect(page.getByTestId('map-view-galaxy')).toBeVisible({ timeout: 5000 });
    await page.getByTestId('map-view-galaxy').click();
    await expect(page.getByTestId('map-snap-top-down')).toBeVisible({ timeout: 5000 });
    await page.getByTestId('map-snap-top-down').click();
    await page.waitForTimeout(500);

    // Check initial state
    const canvas = await page.locator('canvas').count();
    expect(canvas).toBeGreaterThan(0);
    console.log(`✓ Canvas rendering: ${canvas}`);

    // Zoom in using wheel events to trigger real-star detail
    console.log('\nZooming in to trigger real-star detail...');

    const renderer = page.locator('.map-foundation-renderer');

    // Register before zooming so a fast response cannot win the listener race.
    const apiCallPromise = page.waitForResponse((response) => (
      new URL(response.url()).pathname === '/api/map/systems'
    ));

    // Cross the LOD deliberately, then let the camera settle. Waiting for the
    // response inside this animation loop races React's settled-camera debounce
    // on slower CI renderers.
    const maxZoomAttempts = 10;
    const zoomStep = 1000;
    let currentZoom = Number(await renderer.getAttribute('data-camera-zoom'));

    for (let i = 0; i < maxZoomAttempts; i++) {
      const previousZoom = currentZoom;
      await renderer.evaluate((element, deltaY) => {
        element.dispatchEvent(new WheelEvent('wheel', {
          bubbles: true,
          cancelable: true,
          deltaY,
        }));
      }, -zoomStep);

      await expect.poll(async () => Number(await renderer.getAttribute('data-camera-zoom')))
        .toBeLessThan(previousZoom);
      currentZoom = Number(await renderer.getAttribute('data-camera-zoom'));
      console.log(`  Step ${i + 1}: Zoom = ${currentZoom} LY/px`);

      if (currentZoom <= 3) break;
    }

    expect(currentZoom, 'Should cross the viewport-span LOD').toBeLessThanOrEqual(3);
    const apiResponse = await apiCallPromise;
    expect(apiResponse.status()).toBe(200);
    const apiBody = await apiResponse.json() as {
      systems: Array<unknown>;
      truncated: boolean;
    };
    expect(apiBody).toEqual(expect.objectContaining({
      systems: expect.any(Array),
      truncated: expect.any(Boolean),
    }));
    const hadApiCall = true;

    // Final verification
    console.log('\n╔════════════════════════════════════════════════════════════╗');
    console.log('║  VERIFICATION RESULTS                                      ║');
    console.log('╚════════════════════════════════════════════════════════════╝');

    console.log(`✓ Canvas rendering: ${canvas > 0 ? 'YES' : 'NO'}`);
    console.log(`✓ Reached real-star LOD: ${hadApiCall ? 'YES' : 'NO'}`);
    console.log(`✓ API calls to /map/systems: ${apiCalls.length > 0 ? 'YES' : 'NO'}`);
    console.log(`✓ Real-star API response received: ${hadApiCall ? 'YES' : 'NO'}`);
    console.log(`✓ Viewport-systems console messages: ${viewportMessages.length > 0 ? 'YES' : 'NO'}`);

    if (apiCalls.length > 0) {
      console.log(`  Tracked calls:`);
      apiCalls.forEach(call => console.log(`    ${call}`));
    }

    if (viewportMessages.length > 0) {
      console.log(`  Viewport messages:`);
      viewportMessages.forEach(msg => console.log(`    ${msg}`));
    }

    // Core assertions
    expect(canvas).toBeGreaterThan(0);
    expect(hadApiCall).toBe(true);
  } finally {
    // Clean up event listeners
    page.off('console', consoleHandler);
    page.off('response', responseHandler);
  }
});
