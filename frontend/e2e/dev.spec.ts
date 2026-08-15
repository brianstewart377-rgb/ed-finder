/**
 * Development-focused test scenarios for manual browser automation.
 *
 * Run with: npx playwright test dev.spec.ts --headed --debug
 *
 * Or use the dev-helpers in your own script for interactive testing.
 */

import { test, expect } from '@playwright/test';
import {
  navigateToMap,
  getCurrentZoom,
  zoomIn,
  zoomOut,
  panMap,
  takeScreenshot,
  testRealStarZoom,
} from './dev-helpers';

test.describe('Map Dev Scenarios', () => {
  test('can navigate and interact with the map', async ({ page }) => {
    // Increase timeout for dev scenarios
    test.setTimeout(60000);

    await navigateToMap(page);
    await page.waitForTimeout(1000);

    const initialZoom = await getCurrentZoom(page);
    console.log(`Initial zoom: ${initialZoom}`);
    await takeScreenshot(page, 'initial-view');

    // Test zoom in
    await zoomIn(page, 3);
    await takeScreenshot(page, 'after-zoom-in');

    // Test pan
    await panMap(page, 100, 50);
    await takeScreenshot(page, 'after-pan');

    // Test zoom out
    await zoomOut(page, 3);
    await takeScreenshot(page, 'after-zoom-out');

    const finalZoom = await getCurrentZoom(page);
    console.log(`Final zoom: ${finalZoom}`);
  });

  test('real-star layer appears when zoomed in enough', async ({ page }) => {
    test.setTimeout(60000);

    await navigateToMap(page);
    await testRealStarZoom(page);
  });

  test('heatmap and real-star layer toggle correctly', async ({ page }) => {
    test.setTimeout(60000);

    await navigateToMap(page);

    // At galaxy view, heatmap should be visible, no real-stars
    console.log('At galaxy view...');
    await takeScreenshot(page, 'heatmap-visible');

    // Zoom in significantly
    console.log('Zooming in...');
    for (let i = 0; i < 10; i++) {
      await zoomIn(page, 1);
      const zoom = await getCurrentZoom(page);
      console.log(`Zoom step ${i + 1}: ${zoom}`);
    }

    await page.waitForTimeout(2000);
    await takeScreenshot(page, 'real-stars-visible');
    console.log('At detailed view - real-stars should be visible');

    // Zoom back out
    console.log('Zooming out...');
    for (let i = 0; i < 10; i++) {
      await zoomOut(page, 1);
    }

    await page.waitForTimeout(2000);
    await takeScreenshot(page, 'back-to-heatmap');
    console.log('Back at galaxy view - heatmap should be visible again');
  });
});
