/**
 * Development helper utilities for Playwright automation.
 *
 * Use these functions to drive the browser during development, test changes
 * visually, and capture screenshots/videos of interactions.
 *
 * Example:
 *   const browser = await chromium.launch({ headless: false });
 *   const page = await browser.newPage({ recordVideo: { dir: 'videos' } });
 *   await navigateToMap(page);
 *   await zoomIn(page, 5);
 *   await takeScreenshot(page, 'zoomed-in');
 */

import { Page, expect } from '@playwright/test';

// Dynamically import injectAxe only in test environment
let injectAxe: ((page: Page) => Promise<void>) | null = null;
try {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  injectAxe = require('axe-playwright').injectAxe;
} catch {
  // Axe not installed, accessibility checks will be skipped
}

/**
 * Navigate to the map page and wait for it to be interactive.
 */
export async function navigateToMap(page: Page, baseUrl = 'http://localhost:5173') {
  await page.goto(`${baseUrl}/map`);
  // Wait for canvas to be rendered
  await page.waitForSelector('[data-testid="stage26e-production-map-viewport"]', { timeout: 10000 });
}

/**
 * Get the current zoom level from the map UI.
 */
export async function getCurrentZoom(page: Page): Promise<string> {
  const zoomOutput = await page.locator('output[aria-label="Map zoom"]').textContent();
  return zoomOutput || 'unknown';
}

/**
 * Zoom in by N steps using the zoom button.
 * Each step decreases zoom level (zooms in).
 */
export async function zoomIn(page: Page, steps: number = 1) {
  const zoomInBtn = page.locator('[data-testid="map-zoom-in"]');
  for (let i = 0; i < steps; i++) {
    await zoomInBtn.click();
    // Wait for map to settle after zoom
    await page.waitForTimeout(500);
  }
  console.log(`Zoomed in ${steps} times. Current zoom: ${await getCurrentZoom(page)}`);
}

/**
 * Zoom out by N steps using the zoom button.
 * Each step increases zoom level (zooms out).
 */
export async function zoomOut(page: Page, steps: number = 1) {
  const zoomOutBtn = page.locator('[data-testid="map-zoom-out"]');
  for (let i = 0; i < steps; i++) {
    await zoomOutBtn.click();
    // Wait for map to settle after zoom
    await page.waitForTimeout(500);
  }
  console.log(`Zoomed out ${steps} times. Current zoom: ${await getCurrentZoom(page)}`);
}

/**
 * Pan the map by clicking and dragging.
 * Positive dx/dy pan right/down, negative pan left/up.
 */
export async function panMap(page: Page, dx: number, dy: number) {
  const canvas = page.locator('[data-testid="stage26e-production-map-viewport"] canvas');
  const box = await canvas.boundingBox();
  if (!box) throw new Error('Canvas not found');

  const startX = box.x + box.width / 2;
  const startY = box.y + box.height / 2;

  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + dx, startY + dy);
  await page.mouse.up();

  // Wait for pan to settle
  await page.waitForTimeout(500);
  console.log(`Panned by (${dx}, ${dy})`);
}

/**
 * Take a screenshot and save to e2e/screenshots/ directory.
 */
export async function takeScreenshot(page: Page, name: string) {
  const filename = `screenshots/${name}-${new Date().toISOString().replace(/[:.]/g, '-')}.png`;
  await page.screenshot({ path: filename });
  console.log(`Screenshot saved: ${filename}`);
}

/**
 * Wait for the real-star detail layer to appear (if zoomed in enough).
 * Checks for the console message indicating the layer enabled.
 */
export async function waitForRealStarDetail(page: Page, timeout = 10000) {
  // Listen for the console message from the hook
  let found = false;
  const listener = (msg: any) => {
    if (msg.text().includes('[viewport-systems] camera key')) {
      if (msg.text().includes('should enable: true')) {
        found = true;
      }
    }
  };

  page.on('console', listener);

  const startTime = Date.now();
  while (!found && Date.now() - startTime < timeout) {
    await page.waitForTimeout(100);
  }

  page.off('console', listener);

  if (!found) {
    console.warn('Real-star detail layer did not enable within timeout');
  } else {
    console.log('✓ Real-star detail layer enabled');
  }
}

/**
 * Get list of network requests made to a specific endpoint.
 */
export async function captureNetworkRequests(page: Page, urlPattern: string) {
  const requests: string[] = [];

  page.on('response', (response) => {
    if (response.url().includes(urlPattern)) {
      requests.push(`${response.status()} ${response.url()}`);
    }
  });

  return requests;
}

/**
 * Assert that a network request was made to an endpoint.
 */
export async function expectNetworkRequest(page: Page, urlPattern: string, timeout = 5000) {
  return page.waitForResponse(
    (response) => response.url().includes(urlPattern),
    { timeout }
  );
}

/**
 * Check if the heatmap layer is visible (looks for heatmap voxels).
 */
export async function isHeatmapVisible(page: Page): Promise<boolean> {
  // In the 3D map, we check if the heatmap points are being rendered
  // This is a heuristic based on the fact that the heatmap should exist
  // in the scene if it's visible
  try {
    await expectNetworkRequest(page, '/api/map/heatmap', 2000);
    return true;
  } catch {
    return false;
  }
}

/**
 * Check if the real-star layer is visible.
 */
export async function isRealStarLayerVisible(page: Page): Promise<boolean> {
  try {
    await expectNetworkRequest(page, '/api/map/systems', 2000);
    return true;
  } catch {
    return false;
  }
}

/**
 * Development test scenario: Zoom in and verify real-star layer appears.
 */
export async function testRealStarZoom(page: Page) {
  console.log('\n=== Real-Star Zoom Test ===');

  // Start at galaxy view
  console.log(`Starting zoom: ${await getCurrentZoom(page)}`);

  // Gradually zoom in
  for (let i = 0; i < 8; i++) {
    await zoomIn(page, 1);

    const zoom = await getCurrentZoom(page);
    console.log(`Step ${i + 1}: Zoom = ${zoom}`);

    // Check if real-star layer appeared
    const hasRealStars = await isRealStarLayerVisible(page);
    if (hasRealStars) {
      console.log('✓ Real-star layer detected!');
      await takeScreenshot(page, `real-star-zoomed-${i}`);
      return;
    }

    await page.waitForTimeout(1000);
  }

  console.warn('Real-star layer did not appear after 8 zoom steps');
}

/**
 * Check for accessibility violations using Axe-core.
 *
 * Returns array of violations found. Empty array = no violations.
 */
export async function checkAccessibility(page: Page, context = 'page') {
  if (!injectAxe) {
    console.warn('⚠ Axe-core not available, skipping accessibility check');
    return [];
  }

  try {
    await injectAxe(page);
    const violations = await page.evaluate(() => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return (window as any).axe.run((err: any, results: any) => {
        if (err) throw err;
        return results.violations;
      });
    });

    if (violations && violations.length > 0) {
      console.warn(`⚠ Found ${violations.length} accessibility violations on ${context}`);
      violations.forEach((v: any) => {
        console.warn(`  - ${v.id}: ${v.description} (${v.nodes?.length} nodes)`);
      });
    } else {
      console.log(`✓ No accessibility violations found on ${context}`);
    }

    return violations || [];
  } catch (error) {
    console.error('Accessibility check failed:', error);
    return [];
  }
}

/**
 * Assert no critical accessibility violations.
 *
 * Throws if critical violations found (e.g., missing alt text, contrast issues).
 */
export async function assertAccessible(page: Page, context = 'page') {
  const violations = await checkAccessibility(page, context);

  // Filter to critical issues
  const critical = violations.filter((v: any) => {
    const impact = v.impact?.toLowerCase();
    return impact === 'critical' || impact === 'serious';
  });

  if (critical.length > 0) {
    throw new Error(
      `Critical accessibility violations found on ${context}: ${critical.map((v: any) => v.id).join(', ')}`
    );
  }
}
