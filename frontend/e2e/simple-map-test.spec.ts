import { test, expect } from '@playwright/test';

test('check map page loads', async ({ page }) => {
  test.setTimeout(30000);

  console.log('\n✓ Navigating to map...');
  await page.goto('http://localhost:5173/map');

  // Wait a bit for the page to load
  await page.waitForTimeout(3000);

  // Log all console messages
  page.on('console', (msg) => {
    console.log(`[CONSOLE] ${msg.type()}: ${msg.text()}`);
  });

  // Log all page errors
  page.on('pageerror', (error) => {
    console.log(`[PAGE ERROR] ${error.message}`);
  });

  // Check what's on the page
  const title = await page.title();
  console.log(`✓ Page title: ${title}`);

  // Check if root element exists
  const root = await page.locator('#root');
  const rootVisible = await root.isVisible().catch(() => false);
  console.log(`✓ Root element visible: ${rootVisible}`);

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

  // Look for map viewport
  const mapViewport = await page.locator('[data-testid="stage26e-production-map-viewport"]').count();
  console.log(`✓ Map viewport elements found: ${mapViewport}`);

  // Check body content
  const bodyText = await page.locator('body').textContent();
  if (bodyText) {
    console.log(`✓ Body text (first 200 chars): ${bodyText.substring(0, 200)}`);
  }

  // Take a screenshot for visual inspection
  await page.screenshot({ path: 'frontend/test-results/simple-map-test.png' });
  console.log(`✓ Screenshot saved`);
});
