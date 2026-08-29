import { test, expect } from '@playwright/test';

test('check map page loads', async ({ page }) => {
  test.setTimeout(60000);

  // Capture console and errors, collect them for assertion (issue #3)
  const pageErrors: string[] = [];
  const consoleMessages: { type: string; text: string }[] = [];

  const consoleHandler = (msg: any) => {
    const entry = { type: msg.type(), text: msg.text() };
    consoleMessages.push(entry);
    console.log(`[CONSOLE] ${entry.type}: ${entry.text}`);
  };
  page.on('console', consoleHandler);

  const errorHandler = (error: Error) => {
    pageErrors.push(error.message);
    console.log(`[PAGE ERROR] ${error.message}`);
  };
  page.on('pageerror', errorHandler);

  const requestHandler = (request: any) => {
    if (request.url().includes('/api/')) {
      console.log(`[REQUEST] ${request.method()} ${request.url().split('?')[0]}`);
    }
  };
  page.on('request', requestHandler);

  const responseHandler = (response: any) => {
    if (response.url().includes('/api/')) {
      console.log(`[RESPONSE] ${response.status()} ${response.url().split('?')[0]}`);
    }
  };
  page.on('response', responseHandler);

  try {
    console.log('\n✓ Navigating to map (hash-based routing: /#map)...');
    await page.goto('/#map');

    // Wait for page to fully load
    await page.waitForTimeout(5000);

    // Check if Map tab exists and click it if needed
    const mapTab = page.locator('button:has-text("Map")').first();
    const mapTabVisible = await mapTab.isVisible().catch(() => false);
    console.log(`✓ Map tab visible: ${mapTabVisible}`);
    if (mapTabVisible) {
      console.log('✓ Clicking Map tab...');
      await mapTab.click();
      await page.waitForTimeout(2000);
    }

    // Check what's on the page
    const title = await page.title();
    console.log(`✓ Page title: ${title}`);

    // Check if root element exists
    const root = await page.locator('#root');
    const rootVisible = await root.isVisible().catch(() => false);
    console.log(`✓ Root element visible: ${rootVisible}`);
    expect(rootVisible).toBe(true);

    // Check for any error messages
    const errorElements = await page.locator('[role="alert"], .error, [class*="error"]').allTextContents();
    if (errorElements.length > 0) {
      console.log(`✗ Errors found: ${errorElements.join(', ')}`);
    } else {
      console.log(`✓ No error elements visible`);
    }

    // Try to find the map canvas with alternate selectors
    const canvas = await page.locator('canvas').count();
    console.log(`✓ Canvas elements found: ${canvas}`);
    expect(canvas).toBeGreaterThan(0);

    // Look for map viewport
    const mapViewport = await page.locator('[data-testid="stage26e-production-map-viewport"]').count();
    console.log(`✓ Map viewport elements found: ${mapViewport}`);

    // Check body content
    const bodyText = await page.locator('body').textContent();
    if (bodyText) {
      console.log(`✓ Body text (first 200 chars): ${bodyText.substring(0, 200)}`);
    }

    // Validate screenshot with baseline (issue #4: screenshot validation)
    await expect(page).toHaveScreenshot('simple-map-test.png', {
      maxDiffPixels: 100, // Allow minor rendering differences
      threshold: 0.2,
    });
    console.log(`✓ Screenshot validated against baseline`);

    // Assert no page errors occurred (issue #3: error validation)
    expect(
      pageErrors,
      `Page errors should not occur. Errors: ${pageErrors.join(', ')}`
    ).toEqual([]);

  } finally {
    // Clean up event listeners
    page.off('console', consoleHandler);
    page.off('pageerror', errorHandler);
    page.off('request', requestHandler);
    page.off('response', responseHandler);
  }
});
