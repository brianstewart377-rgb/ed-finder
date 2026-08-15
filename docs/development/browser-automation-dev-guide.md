# Browser Automation Development Guide

## Quick Start

Once your local dev environment is running (`make dev`), you can use Playwright to automate browser interactions and visually test your changes.

### Running Interactive Dev Tests

```bash
# View your changes in a real browser with debug UI
make dev-test

# Same, but record videos of interactions
make dev-test-video
```

The browser will open with full Playwright controls. You can:
- **Step through** test scenarios manually
- **Pause/resume** execution
- **Inspect elements** in DevTools
- **Watch** your changes in real-time
- **Screenshots** are automatically saved to `frontend/screenshots/`

### Using Dev Helpers in Your Own Tests

The `frontend/e2e/dev-helpers.ts` file provides utilities for common map interactions:

```typescript
import {
  navigateToMap,
  zoomIn,
  panMap,
  takeScreenshot,
  waitForRealStarDetail,
} from './dev-helpers';

// Navigate to map
await navigateToMap(page);

// Zoom in 5 times (each zooms in more)
await zoomIn(page, 5);

// Pan the map
await panMap(page, 100, 50);  // dx=100, dy=50

// Take a screenshot
await takeScreenshot(page, 'my-test-screenshot');

// Wait for real-star layer to enable when zoomed in
await waitForRealStarDetail(page);
```

## Available Dev Helpers

| Function | Purpose | Example |
|----------|---------|---------|
| `navigateToMap()` | Go to map page | `await navigateToMap(page);` |
| `getCurrentZoom()` | Get zoom level | `const z = await getCurrentZoom(page);` |
| `zoomIn(n)` | Zoom in N steps | `await zoomIn(page, 3);` |
| `zoomOut(n)` | Zoom out N steps | `await zoomOut(page, 3);` |
| `panMap(dx, dy)` | Pan by pixels | `await panMap(page, 100, 50);` |
| `takeScreenshot(name)` | Save screenshot | `await takeScreenshot(page, 'test');` |
| `waitForRealStarDetail()` | Wait for stars layer | `await waitForRealStarDetail(page);` |
| `isHeatmapVisible()` | Check heatmap visible | `const v = await isHeatmapVisible(page);` |
| `isRealStarLayerVisible()` | Check stars visible | `const v = await isRealStarLayerVisible(page);` |

## Common Development Scenarios

### Test a Map Change

```typescript
test('my new map feature', async ({ page }) => {
  // Increase timeout for interactive tests
  test.setTimeout(60000);

  await navigateToMap(page);
  
  // Your test code here
  await zoomIn(page, 5);
  await takeScreenshot(page, 'feature-screenshot');
  
  // Assert something changed
  expect(someElement).toBeVisible();
});
```

### Verify Real-Star Zoom Behavior

```typescript
test('real-stars appear on zoom', async ({ page }) => {
  test.setTimeout(60000);
  
  await navigateToMap(page);
  
  // Gradually zoom in and watch for real-stars
  for (let i = 0; i < 8; i++) {
    await zoomIn(page, 1);
    const hasStars = await isRealStarLayerVisible(page);
    
    if (hasStars) {
      console.log(`Real-stars appeared at step ${i}`);
      break;
    }
  }
});
```

### Capture Screenshots During Development

```typescript
test('capture map states', async ({ page }) => {
  test.setTimeout(60000);

  await navigateToMap(page);
  await takeScreenshot(page, 'galaxy-view');
  
  await zoomIn(page, 5);
  await takeScreenshot(page, 'zoomed-view');
  
  await panMap(page, 200, 100);
  await takeScreenshot(page, 'panned-view');
});
```

Screenshots are saved to `frontend/screenshots/` with timestamps.

## Debugging Tips

### View Network Requests
The dev helpers track `/api/map/*` requests. Console output shows which endpoints are called and when.

### Check Console Messages
The real-star viewport hook logs to console:
```
[viewport-systems] camera key: 1000|2000|5|0 should enable: true
```
This indicates the layer detected a zoom threshold.

### Use Playwright Inspector
Run with `--debug` flag to open the Inspector:
```bash
cd frontend && npx playwright test e2e/dev.spec.ts --headed --debug
```

In the Inspector, you can:
- Step through each action
- Inspect DOM elements
- Execute JS in console
- Take screenshots manually

### Video Recording
If tests fail, videos are saved to `test-results/`:
```bash
make dev-test-video
# Videos in: frontend/test-results/
```

## Troubleshooting

**"Canvas not found"**
- Ensure map has loaded (`await page.waitForSelector('[data-testid="..."]')`)
- Check that the URL is correct

**"Real-stars never appear"**
- Check browser console for errors (`[viewport-systems] camera key` messages)
- Verify API is returning data (`/api/map/systems` requests)
- Check zoom threshold constants in `viewportSystems.ts`

**Screenshots not saved**
- Ensure `frontend/screenshots/` directory exists
- Check file permissions

## Adding New Dev Helpers

To add a new helper function, edit `frontend/e2e/dev-helpers.ts`:

```typescript
/**
 * Short description of what this does.
 */
export async function myNewHelper(page: Page, arg1: string) {
  // Implementation
  console.log(`Performing action: ${arg1}`);
}
```

Then use it in tests:
```typescript
import { myNewHelper } from './dev-helpers';

test('my test', async ({ page }) => {
  await myNewHelper(page, 'value');
});
```

## Related

- `frontend/e2e/dev.spec.ts` — Example test scenarios
- `frontend/e2e/smoke.spec.ts` — Production E2E tests
- `frontend/playwright.config.ts` — Playwright configuration
