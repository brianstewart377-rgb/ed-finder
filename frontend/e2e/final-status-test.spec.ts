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

test('comprehensive E2E status check', async ({ page, request }) => {
  test.setTimeout(60000);

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║        COMPREHENSIVE E2E STATUS CHECK                       ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  // Capture page errors (for robustness)
  const pageErrors: string[] = [];
  const errorHandler = (error: Error) => {
    pageErrors.push(error.message);
    console.log(`[PAGE ERROR] ${error.message}`);
  };
  page.on('pageerror', errorHandler);

  try {
    // API health
    const apiResponse = await request.get('/api/health');
    expect(apiResponse.ok()).toBe(true);
    const apiHealth = await apiResponse.json();
    console.log('✓ API Status:', JSON.stringify(apiHealth));

    // Navigate to app using hash-based routing
    console.log('\n✓ Navigating to /#map (hash-based routing)...');
    await page.goto('/#map');
    await page.waitForTimeout(5000);

    // Capture all info
    const title = await page.title();
    console.log(`✓ Page Title: ${title}`);

    const url = page.url();
    console.log(`✓ Current URL: ${url}`);

    // Check for canvas
    const canvasCount = await page.locator('canvas').count();
    console.log(`✓ Canvas Elements: ${canvasCount}`);
    expect(canvasCount).toBeGreaterThan(0);

    // Check for map viewport
    const viewportCount = await page.locator('[data-testid="stage26e-production-map-viewport"]').count();
    console.log(`✓ Map Viewport Elements: ${viewportCount}`);

    // Check for Three.js scene
    const sceneElements = await page.locator('[class*="scene"],[data-testid*="scene"]').count();
    console.log(`✓ Scene Elements: ${sceneElements}`);

    // Capture console logs
    const consoleLogs: string[] = [];
    const consoleHandler = (msg: ConsoleMessage) => {
      const text = msg.text();
      if (text.includes('[viewport-systems]') || text.includes('Real') || text.includes('Stars')) {
        consoleLogs.push(text);
        console.log(`  [CONSOLE] ${text}`);
      }
    };
    page.on('console', consoleHandler);

    // Check API calls
    const apiCalls: { method: string; url: string }[] = [];
    const responseHandler = (response: Response) => {
      if (response.url().includes('/api/map')) {
        apiCalls.push({
          method: 'GET',
          url: response.url().split('?')[0]
        });
        console.log(`  [API] ${response.status()} ${response.url().split('?')[0]}`);
      }
    };
    page.on('response', responseHandler);

    // Wait for any potential API calls
    await page.waitForTimeout(3000);

    console.log('\n╔════════════════════════════════════════════════════════════╗');
    console.log('║  SUMMARY                                                     ║');
    console.log('╚════════════════════════════════════════════════════════════╝');
    console.log(`✓ API Connected: ${apiHealth.status === 'ok' ? 'YES' : 'NO'}`);
    console.log(`✓ Frontend Loaded: YES`);
    console.log(`✓ Canvas Detected: ${canvasCount > 0 ? 'YES' : 'PENDING/NO'}`);
    console.log(`✓ Map Viewport Detected: ${viewportCount > 0 ? 'YES' : 'PENDING/NO'}`);
    console.log(`✓ Real-Star Viewport Hook: ${consoleLogs.length > 0 ? 'ACTIVE' : 'INACTIVE'}`);
    console.log(`✓ Map Systems API Calls: ${apiCalls.length}`);

    // Exercise a real browser capture after the map is ready. These diagnostics
    // intentionally avoid a pixel baseline because no deterministic baseline is
    // checked into the repository and the seeded map content evolves.
    const screenshot = await page.screenshot({ animations: 'disabled', caret: 'hide' });
    expect(screenshot.byteLength).toBeGreaterThan(1_000);
    console.log('\n✓ Screenshot captured');

    // Assert no page errors occurred
    expect(
      pageErrors,
      `Page errors should not occur. Errors: ${pageErrors.join(', ')}`
    ).toEqual([]);

    // Clean up handlers
    page.off('console', consoleHandler);
    page.off('response', responseHandler);

  } finally {
    page.off('pageerror', errorHandler);
  }
});
