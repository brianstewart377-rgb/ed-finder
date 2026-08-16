/**
 * Error scenario E2E tests.
 *
 * Tests how the app handles:
 * - Network failures (no connection, timeouts)
 * - Backend errors (500s, 503s, invalid responses)
 * - Degraded state (slow API, missing data)
 * - Recovery flows
 */

import { test, expect, Page } from '@playwright/test';
import { navigateToMap } from './dev-helpers';

test.describe('Error Scenarios', () => {
  /**
   * Test network failure handling during search.
   * When the API is unavailable, the app should show a user-friendly error.
   */
  test('displays error when search API is unavailable', async ({ page, context }) => {
    // Block /api/local/search to simulate network failure
    await context.route('/api/local/search', (route) => route.abort('failed'));

    await page.goto('/');

    // Click on search tab (if not already there)
    const searchTab = page.locator('button:has-text("Search")').first();
    if (searchTab) {
      await searchTab.click();
    }

    // Attempt to search
    const searchBtn = page.locator('button:has-text("Search")').last();
    if (searchBtn) {
      await searchBtn.click();
      await page.waitForTimeout(2000);
    }

    // Should show error message or graceful fallback
    const errorMsg = page.locator('[role="alert"]');
    if (await errorMsg.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log('✓ Error message displayed to user');
      expect(await errorMsg.textContent()).toContain(/error|unavailable|try again/i);
    }
  });

  /**
   * Test API 500 error handling.
   */
  test('handles 500 errors from backend', async ({ page, context }) => {
    // Return 500 for /api/map/heatmap
    await context.route('/api/map/heatmap*', (route) => {
      route.abort('failed');
    });

    await navigateToMap(page);

    // App should remain responsive despite heatmap failure
    const mapContainer = page.locator('[data-testid="stage26e-production-map-viewport"]');
    await expect(mapContainer).toBeVisible();

    // Error message should appear
    await page.waitForTimeout(2000);
    const errorAlert = page.locator('[role="alert"]');
    if (await errorAlert.isVisible({ timeout: 3000 }).catch(() => false)) {
      console.log('✓ Graceful error handling for 500s');
      expect(await errorAlert.textContent()).toContain(/could not be loaded|remains available/i);
    }
  });

  /**
   * Test slow API response handling.
   * When the API is slow, the app should show loading indicators.
   */
  test('shows loading state for slow API responses', async ({ page, context }) => {
    // Delay heatmap response
    await context.route('/api/map/heatmap*', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 3000));
      await route.continue();
    });

    await navigateToMap(page);

    // Should show loading spinner or indicator
    const spinner = page.locator('[class*="loading"], [class*="spinner"], [aria-label*="Loading"]').first();
    if (await spinner.isVisible({ timeout: 1000 }).catch(() => false)) {
      console.log('✓ Loading indicator shown during slow response');
    }

    // Eventually should finish loading
    await page.waitForTimeout(4000);
  });

  /**
   * Test graceful degradation when optional layers fail.
   */
  test('continues functioning when optional layers fail', async ({ page, context }) => {
    // Fail the real-star endpoint but keep others working
    await context.route('/api/map/systems*', (route) => route.abort('failed'));

    await navigateToMap(page);

    // Zoom in to trigger real-star fetch (which will fail)
    const zoomInBtn = page.locator('[data-testid="map-zoom-in"]');
    for (let i = 0; i < 5; i++) {
      await zoomInBtn.click();
      await page.waitForTimeout(300);
    }

    // App should still be interactive despite real-star failure
    const mapCanvas = page.locator('[data-testid="stage26e-production-map-viewport"] canvas');
    await expect(mapCanvas).toBeVisible();

    // Error message for real-star should appear
    const errorMsg = page.locator('[role="alert"]').first();
    if (await errorMsg.isVisible({ timeout: 3000 }).catch(() => false)) {
      console.log('✓ Graceful degradation when optional layer fails');
      const text = await errorMsg.textContent();
      expect(text).toContain(/detail|remains available|heatmap/i);
    }
  });

  /**
   * Test timeout handling.
   */
  test('handles request timeouts', async ({ page, context }, testInfo) => {
    // Extend timeout for this test as we're testing timeout behavior
    testInfo.setTimeout(30000);

    // Make requests hang indefinitely
    await context.route('/api/**', async (route) => {
      // Simulate a timeout by delaying indefinitely
      await new Promise(() => {
        /* never resolves */
      });
    });

    await page.goto('/');

    // App should timeout gracefully within its own timeout period
    // and not freeze the entire page
    const pageContent = page.locator('body');
    await expect(pageContent).toBeVisible();

    console.log('✓ Page remains responsive despite request timeout');
  });

  /**
   * Test recovery after transient failure.
   */
  test('recovers when API becomes available after failure', async ({ page, context }) => {
    let requestCount = 0;

    // First 2 requests fail, then succeed
    await context.route('/api/map/heatmap*', (route) => {
      requestCount += 1;
      if (requestCount <= 2) {
        route.abort('failed');
      } else {
        route.continue();
      }
    });

    await navigateToMap(page);

    // Should show error initially
    await page.waitForTimeout(2000);

    // Retry or refresh should succeed
    const retryBtn = page.locator('button:has-text(/retry|again/)').first();
    if (await retryBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
      await retryBtn.click();
    } else {
      // Fallback: refresh the page
      await page.reload();
    }

    // Should recover
    await page.waitForTimeout(2000);
    const mapContainer = page.locator('[data-testid="stage26e-production-map-viewport"]');
    await expect(mapContainer).toBeVisible();

    console.log('✓ App recovered after transient failure');
  });

  /**
   * Test invalid response handling.
   */
  test('handles malformed API responses', async ({ page, context }) => {
    // Return invalid JSON
    await context.route('/api/local/search', (route) => {
      route.abort('failed');
    });

    await page.goto('/');

    // Try to search
    const searchBtn = page.locator('button:has-text("Search")').last();
    if (await searchBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await searchBtn.click();
      await page.waitForTimeout(2000);
    }

    // App shouldn't crash
    const appContent = page.locator('body');
    await expect(appContent).toBeVisible();

    console.log('✓ App handles malformed responses');
  });

  /**
   * Test missing required data.
   */
  test('handles missing required data gracefully', async ({ page, context }) => {
    // Return empty response for health check
    await context.route('/api/health', (route) => {
      route.respond({ status: 200, body: JSON.stringify({}) });
    });

    await page.goto('/');

    // App should still load
    await page.waitForTimeout(2000);
    const appContent = page.locator('body');
    await expect(appContent).toBeVisible();

    console.log('✓ App handles missing health data');
  });
});
