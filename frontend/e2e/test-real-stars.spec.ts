import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  // Clear state between tests (issue #10: test isolation)
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
});

test('real-star layer renders when zoomed in', async ({ page }) => {
  test.setTimeout(60000);

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║         REAL-STAR LAYER ZOOM DETECTION TEST               ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  // Capture console logs and API calls
  const viewportMessages: string[] = [];
  const apiCalls: string[] = [];

  const consoleHandler = (msg: any) => {
    const text = msg.text();
    if (text.includes('[viewport-systems]')) {
      viewportMessages.push(text);
      console.log(`[VIEWPORT] ${text}`);
    }
  };
  page.on('console', consoleHandler);

  // Intercept API calls to detect /map/systems requests
  const responseHandler = (response: any) => {
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

    // Set up API response listener with proper race condition handling (issue #1)
    let hadApiCall = false;
    const apiCallPromise = page.waitForResponse((response) => {
      const isRealStarsCall = new URL(response.url()).pathname === '/api/map/systems';
      if (isRealStarsCall) {
        console.log('[API] Real-star API call detected:', response.status());
        hadApiCall = true;
      }
      return isRealStarsCall;
    });

    // Adaptive zoom polling instead of hard-coded timing (issue #6)
    let reachedTarget = false;
    const maxZoomAttempts = 20;
    const targetZoomMin = 20;
    const targetZoomMax = 150;
    const zoomStep = 1000;

    for (let i = 0; i < maxZoomAttempts; i++) {
      await renderer.evaluate((element) => {
        element.dispatchEvent(new WheelEvent('wheel', {
          bubbles: true,
          cancelable: true,
          deltaY: -zoomStep,
        }));
      });

      await page.waitForTimeout(100);

      const currentZoom = await renderer.evaluate((element) => {
        return Number((element as any).dataset.cameraZoom);
      });
      console.log(`  Step ${i + 1}: Zoom = ${currentZoom} LY/px`);

      if (currentZoom >= targetZoomMin && currentZoom <= targetZoomMax) {
        reachedTarget = true;
        console.log(`  ✓ Reached target zoom range (${currentZoom} LY/px)`);
        break;
      }

      if (currentZoom > targetZoomMax) {
        console.log('  ⚠ Zoom exceeded target, stopping');
        break;
      }
    }

    expect(reachedTarget, 'Should reach zoom level suitable for real-star detail').toBe(true);

    // Wait for API response with proper error handling (issue #1)
    try {
      await Promise.race([
        apiCallPromise,
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('Real-stars API did not fire within 10s')), 10000)
        )
      ]);
    } catch (e) {
      if (!hadApiCall) {
        throw e;
      }
      // API fired but response still resolving; wait a bit more
      await page.waitForTimeout(500);
    }

    // Final verification
    console.log('\n╔════════════════════════════════════════════════════════════╗');
    console.log('║  VERIFICATION RESULTS                                      ║');
    console.log('╚════════════════════════════════════════════════════════════╝');

    console.log(`✓ Canvas rendering: ${canvas > 0 ? 'YES' : 'NO'}`);
    console.log(`✓ Reached target zoom: ${reachedTarget ? 'YES' : 'NO'}`);
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
    expect(reachedTarget).toBe(true);
    expect(hadApiCall).toBe(true);
  } finally {
    // Clean up event listeners
    page.off('console', consoleHandler);
    page.off('response', responseHandler);
  }
});
