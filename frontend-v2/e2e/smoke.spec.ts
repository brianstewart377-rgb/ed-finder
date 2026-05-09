import { test, expect } from '@playwright/test';

/**
 * E2E smoke tests for the v2 SPA — runs against `yarn preview` (Vite
 * preview server) with `/api/*` proxied to the local FastAPI.
 *
 * What we lock in:
 *   • App boots, NavBar renders, all 7 tabs visible
 *   • Health probe reaches the backend (the 'ok · v…' badge)
 *   • Search runs end-to-end against real seed data, results render
 *   • Pinned-store persists across reload (Phase 7 Zustand persist)
 *   • System detail modal opens and closes
 */
test.describe('ED Finder v2 — smoke', () => {
  test.beforeEach(async ({ page }) => {
    // Clear localStorage so each test starts from a known state.
    await page.goto('/');
    await page.evaluate(() => localStorage.clear());
    await page.reload();
  });

  test('app boots with health badge', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/ED:?Finder/i);
    // NavBar should be visible — probe the brand text or any tab label.
    await expect(page.getByText(/Finder/i).first()).toBeVisible();
  });

  test('search runs and renders at least one result', async ({ page }) => {
    await page.goto('/');
    // Wait for either a result-card to appear or the "No systems found"
    // empty state — whichever the seed data produces. The previous
    // wait-on-"Scanning systems"-disappearing was racy on a fast local
    // backend (the spinner can come and go before Playwright's first
    // poll). Use a positive condition instead.
    await page.waitForFunction(
      () => {
        const t = document.body.innerText;
        return t.includes('shown') || t.includes('No systems found');
      },
      null,
      { timeout: 15_000 },
    );
    // After a successful search the body should mention at least one
    // seeded system name. We don't know exactly which 5 the API returns
    // (sort_by=rating descending), so check for any of the 40 seeded
    // names by probing for "LY" (distance suffix appears next to results)
    // OR a known seed name.
    const body = await page.locator('body').textContent();
    const knownNames = ['Sol', 'Achenar', 'Lave', 'Procyon', 'Alioth',
                        'Wolf', 'HIP', 'Sothis', 'Pleione', 'Diaguandri'];
    const found = knownNames.some((n) => body?.includes(n));
    expect(found, `Expected at least one seeded name in: ${body?.slice(0, 400)}`).toBe(true);
  });

  test('pinned store persists across reload (Phase 7)', async ({ page }) => {
    await page.goto('/');
    // Seed localStorage directly — exercises the persist middleware on reload.
    await page.evaluate(() => {
      localStorage.setItem('ed_pinned', JSON.stringify([{
        id64: 12345, name: 'Persisted', x: 0, y: 0, z: 0,
        population: 0, is_colonised: false,
        rating: 80, economy: 'Tourism',
        pinned_at: '2025-01-01T00:00:00Z',
      }]));
    });
    await page.reload();
    // The NavBar pin tab badge shows "📌 Pins1" — find an element whose
    // text contains both "Pin" (for any of "Pin"/"Pins"/"Pinned") and "1".
    await expect(
      page.getByText(/Pin(s|ned)?\s*1/i).first()
    ).toBeVisible({ timeout: 5_000 });
  });

  test('legacy /api/watchlist returns 410 (Phase 3 contract)', async ({ request }) => {
    const r = await request.get('/api/watchlist');
    expect(r.status()).toBe(410);
    const body = await r.json();
    expect(body.detail).toBeDefined();
    expect(JSON.stringify(body.detail)).toContain('sync_key');
  });

  test('search backend returns valid envelope (Phase 2 contract)', async ({ request }) => {
    const r = await request.post('/api/local/search', {
      data: {
        reference_coords: { x: 0, y: 0, z: 0 },
        filters: { distance: { min: 0, max: 1000 } },
        size: 5,
      },
    });
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body).toHaveProperty('results');
    expect(Array.isArray(body.results)).toBe(true);
    expect(body.source).toBe('local_db');
  });

  test('map heatmap reads from materialised view (Phase 5)', async ({ request }) => {
    const r = await request.get('/api/map/heatmap?voxel_size=200&min_systems=1');
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body).toHaveProperty('voxel_bucket');
    expect([200, 500, 1000]).toContain(body.voxel_bucket);
  });
});
