import { test, expect } from '@playwright/test';

test('real-star layer renders when zoomed in', async ({ page }) => {
  test.setTimeout(60000);
  await page.emulateMedia({ reducedMotion: 'reduce' });

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
  let hadApiCall = false;
  const responseHandler = (response: any) => {
    if (new URL(response.url()).pathname === '/api/map/systems') {
      const status = response.status();
      apiCalls.push(`${response.url()} → ${status}`);
      hadApiCall = true;
      console.log(`[API] GET /map/systems → ${status}`);
    }
  };
  page.on('response', responseHandler);

  try {
    console.log('Navigating to map...');
    await page.goto('/#map');

    console.log('Setting up map view...');
    await expect(page.getByTestId('map-view-galaxy')).toBeVisible({ timeout: 5000 });
    await page.getByTestId('map-view-galaxy').click();
    await expect(page.getByTestId('map-snap-top-down')).toBeVisible({ timeout: 5000 });
    await page.getByTestId('map-snap-top-down').click();

    const canvas = await page.locator('canvas').count();
    expect(canvas).toBeGreaterThan(0);
    console.log(`✓ Canvas rendering: ${canvas}`);

    console.log('\nZooming in with the production control until real-star detail is requested...');
    const renderer = page.locator('.map-foundation-renderer');
    const zoomIn = page.getByTestId('map-zoom-in');
    const realStarsResponsePromise = page.waitForResponse(
      (response) => new URL(response.url()).pathname === '/api/map/systems',
      { timeout: 30000 },
    );

    for (let attempt = 0; attempt < 24 && !hadApiCall; attempt += 1) {
      const before = Number(await renderer.getAttribute('data-camera-zoom'));
      await zoomIn.click();
      await expect.poll(
        async () => Number(await renderer.getAttribute('data-camera-zoom')),
        { timeout: 3000 },
      ).toBeLessThan(before);
      const after = Number(await renderer.getAttribute('data-camera-zoom'));
      console.log(`  Step ${attempt + 1}: ${before.toFixed(3)} → ${after.toFixed(3)} LY/px`);
      // The viewport hook deliberately waits 250 ms after camera movement
      // before issuing the detail query; give that production debounce room.
      await page.waitForTimeout(350);
    }

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

    console.log('\n╔════════════════════════════════════════════════════════════╗');
    console.log('║  VERIFICATION RESULTS                                      ║');
    console.log('╚════════════════════════════════════════════════════════════╝');
    console.log(`✓ Canvas rendering: ${canvas > 0 ? 'YES' : 'NO'}`);
    console.log(`✓ API calls to /map/systems: ${apiCalls.length > 0 ? 'YES' : 'NO'}`);
    console.log(`✓ Real-star API response received: ${hadApiCall ? 'YES' : 'NO'}`);
    console.log(`✓ Viewport-systems console messages: ${viewportMessages.length > 0 ? 'YES' : 'NO'}`);

    expect(canvas).toBeGreaterThan(0);
    expect(hadApiCall).toBe(true);
  } finally {
    page.off('console', consoleHandler);
    page.off('response', responseHandler);
  }
});
