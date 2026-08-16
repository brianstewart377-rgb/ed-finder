import { test, expect } from '@playwright/test';

test('real-star layer renders when zoomed in', async ({ page }) => {
  test.setTimeout(60000);

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║         REAL-STAR LAYER ZOOM DETECTION TEST               ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  // Capture console logs and API calls
  const viewportMessages: string[] = [];
  const apiCalls: string[] = [];

  page.on('console', (msg) => {
    const text = msg.text();
    if (text.includes('[viewport-systems]')) {
      viewportMessages.push(text);
      console.log(`[VIEWPORT] ${text}`);
    }
  });

  // Intercept API calls to detect /map/systems requests
  page.on('response', (response) => {
    if (response.url().includes('/api/map/systems')) {
      const status = response.status();
      apiCalls.push(`${response.url()} → ${status}`);
      console.log(`[API] GET /map/systems → ${status}`);
    }
  });

  // Navigate to map with setup steps matching the passing smoke test
  console.log('Navigating to map...');
  await page.goto('/#map');
  await page.waitForLoadState('networkidle');

  // Set up the view (matching smoke.spec.ts setup)
  console.log('Setting up map view...');
  await page.getByTestId('map-view-galaxy').click().catch(() => {});
  await page.getByTestId('map-snap-top-down').click().catch(() => {});
  await page.waitForTimeout(500);  // Let view settle

  // Check initial state
  let canvas = await page.locator('canvas').count();
  expect(canvas).toBeGreaterThan(0);
  console.log(`✓ Canvas rendering: ${canvas}`);

  // Zoom in using wheel events (same as smoke test) to trigger real-star detail
  console.log('\nZooming in to trigger real-star detail...');

  const renderer = page.locator('.map-foundation-renderer');

  // Set up API response listener BEFORE zooming
  let hadApiCall = false;
  const apiCallPromise = new Promise<boolean>((resolve) => {
    const checkResponse = (response: any) => {
      try {
        if (new URL(response.url()).pathname === '/api/map/systems') {
          console.log('[API] Real-star API call detected:', response.status());
          hadApiCall = true;
          page.removeListener('response', checkResponse);
          resolve(true);
        }
      } catch (e) {
        // Ignore errors parsing URL
      }
    };
    page.on('response', checkResponse);

    // Set a timeout in case the API never fires
    setTimeout(() => {
      page.removeListener('response', checkResponse);
      resolve(false);
    }, 10000);
  });

  // Dispatch wheel events to zoom in
  let reachedTarget = false;
  for (let i = 0; i < 10; i++) {
    await renderer.evaluate((element) => {
      element.dispatchEvent(new WheelEvent('wheel', {
        bubbles: true,
        cancelable: true,
        deltaY: -500,  // Zoom in
      }));
    });

    await page.waitForTimeout(300);  // Wait for camera update + settle timer

    const currentZoom = await renderer.getAttribute('data-camera-zoom');
    console.log(`  Step ${i + 1}: Zoom = ${currentZoom} LY/px`);

    // Real-star detail should trigger around zoom level 80-120
    const zoomNum = parseFloat(currentZoom ?? '0');
    if (zoomNum >= 80 && zoomNum <= 120) {
      reachedTarget = true;
      console.log(`  ✓ Reached target zoom range (${zoomNum} LY/px)`);
      break;
    }
  }

  // Wait for the API response (or timeout)
  hadApiCall = await apiCallPromise;

  // Final verification
  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║  VERIFICATION RESULTS                                      ║');
  console.log('╚════════════════════════════════════════════════════════════╝');

  console.log(`✓ Canvas rendering: ${canvas > 0 ? 'YES' : 'NO'}`);
  console.log(`✓ Reached target zoom: ${reachedTarget ? 'YES' : 'NO'}`);
  console.log(`✓ API calls to /map/systems (via page.on): ${apiCalls.length > 0 ? 'YES' : 'NO'}`);
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
  expect(reachedTarget).toBe(true);  // Should reach target zoom
  expect(hadApiCall).toBe(true);  // API should have been called once zoomed in
});
