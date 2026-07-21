import { expect, test } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

type Candidate = 'deckgl-orbit' | 'deckgl-ortho' | 'threejs-r3f';
type Dataset = 100_000 | 500_000;
type Result = {
  candidateId: Candidate;
  datasetSize: Dataset;
  viewportWidth: number;
  viewportHeight: number;
  browser: string;
  os: string;
  timestamp: string;
  measurements: Record<string, number | boolean | null>;
  scenarioStatuses: Record<string, 'pass' | 'fail'>;
  fixtureFailures: string[];
  legalConclusion: 'unresolved';
  notes: string;
};

const candidates: Candidate[] = ['deckgl-orbit', 'deckgl-ortho', 'threejs-r3f'];
const datasets: Dataset[] = [100_000, 500_000];
const viewports = [{ width: 1280, height: 720 }, { width: 1440, height: 900 }];
const results: Result[] = [];

function percentile(values: number[], fraction: number): number | null {
  if (values.length === 0) return null;
  const ordered = [...values].sort((left, right) => left - right);
  return ordered[Math.min(ordered.length - 1, Math.floor(ordered.length * fraction))];
}

test.afterAll(async () => {
  const outputDir = path.resolve(process.cwd(), '../artifacts/map-foundation/stage-26b');
  await mkdir(outputDir, { recursive: true });
  await writeFile(path.join(outputDir, 'map-bakeoff-results.json'), `${JSON.stringify({
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    environment: { platform: os.platform(), release: os.release(), cpu: os.cpus()[0]?.model ?? 'unknown' },
    results,
  }, null, 2)}\n`);
});

for (const viewport of viewports) {
  for (const candidate of candidates) {
    for (const dataset of datasets) {
      test(`${candidate} ${dataset} at ${viewport.width}x${viewport.height}`, async ({ page, browserName }) => {
        const consoleErrors: string[] = [];
        page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
        await page.setViewportSize(viewport);
        await page.goto(`/bakeoff/index.html?candidate=${candidate}&dataset=${dataset}`);
        await expect(page.getByTestId('ready')).toHaveText('ready');
        await page.waitForFunction(() => (window.__stage26bBakeoff?.snapshot().frameTimesMs.length ?? 0) >= 30);

        const canvas = page.locator('canvas').first();
        const box = await canvas.boundingBox();
        expect(box).not.toBeNull();
        if (box) {
          await canvas.click({ position: { x: box.width / 2 + 250, y: box.height / 2 } });
        }
        await page.waitForTimeout(100);
        const beforeContextLoss = await page.evaluate(() => window.__stage26bBakeoff!.snapshot());
        expect(beforeContextLoss.selectedId64).toBe(100_000_000);
        expect(beforeContextLoss.clickLatencyMs).not.toBeNull();

        const contextLossRecoveryMs = await page.evaluate(async () => {
          const canvas = document.querySelector('canvas');
          const gl = canvas?.getContext('webgl2') ?? canvas?.getContext('webgl');
          const extension = gl?.getExtension('WEBGL_lose_context');
          if (!canvas || !extension) return null;
          return new Promise<number | null>((resolve) => {
            const startedAt = performance.now();
            const timeout = window.setTimeout(() => resolve(null), 5_000);
            canvas.addEventListener('webglcontextlost', (event) => {
              event.preventDefault();
              window.setTimeout(() => extension.restoreContext(), 50);
            }, { once: true });
            canvas.addEventListener('webglcontextrestored', () => {
              window.clearTimeout(timeout);
              resolve(performance.now() - startedAt);
            }, { once: true });
            extension.loseContext();
          });
        });
        await page.waitForTimeout(250);
        if (box) {
          await canvas.click({ position: { x: box.width / 2 + 250, y: box.height / 2 } });
        }
        await page.waitForTimeout(100);

        const snapshot = await page.evaluate(() => window.__stage26bBakeoff!.snapshot());
        const contextRecoveryUsable = snapshot.selectionCount > beforeContextLoss.selectionCount;
        const memoryBytes = await page.evaluate(() => {
          const memory = performance as Performance & { memory?: { usedJSHeapSize: number } };
          return memory.memory?.usedJSHeapSize ?? null;
        });
        expect(snapshot.fixtureFailures).toEqual([]);
        expect(consoleErrors).toEqual([]);
        expect(Object.keys(snapshot.fixtureResults)).toHaveLength(17);
        expect(snapshot.regionLabelCount).toBe(42);
        expect(snapshot.regionBoundaryCount).toBeGreaterThan(0);
        expect(contextLossRecoveryMs).not.toBeNull();

        const settledFrames = snapshot.frameTimesMs.slice(5);
        results.push({
          candidateId: candidate,
          datasetSize: dataset,
          viewportWidth: viewport.width,
          viewportHeight: viewport.height,
          browser: browserName,
          os: `${os.platform()} ${os.release()}`,
          timestamp: new Date().toISOString(),
          measurements: {
            frameTimeP50Ms: percentile(settledFrames, 0.50),
            frameTimeP95Ms: percentile(settledFrames, 0.95),
            frameTimeP99Ms: percentile(settledFrames, 0.99),
            initialLoadMs: snapshot.initialLoadMs,
            clickLatencyMs: beforeContextLoss.clickLatencyMs,
            memoryUsageMB: memoryBytes == null ? null : memoryBytes / 1_048_576,
            compressedBundleBytes: null,
            contextLossRecoveryMs,
            regionCorrectness: snapshot.regionLabelCount === 42 ? 1 : 0,
            overlapHandlingCorrect: snapshot.fixtureResults.overlapKeyboardFixture === 'pass',
            keyboardWorkflowCorrect: ['keyboardSystemTraversalFixture', 'keyboardOverlayToggleFixture', 'keyboardSearchResultFixture']
              .every((key) => snapshot.fixtureResults[key] === 'pass'),
            scenarioResultsPassed: Object.values(snapshot.fixtureResults).filter((status) => status === 'pass').length,
            gpuFrameTimeMs: null,
          },
          scenarioStatuses: {
            ...snapshot.fixtureResults,
            rendererContextRecovery: contextRecoveryUsable ? 'pass' : 'fail',
          },
          fixtureFailures: snapshot.fixtureFailures,
          legalConclusion: 'unresolved',
          notes: `Automated Chromium bake-off; context recovery is timed to the WebGL restored event and post-recovery picking ${contextRecoveryUsable ? 'passed' : 'failed'}. GPU timing, compressed per-candidate bundle size, and legal conclusion remain unresolved.`,
        });
      });
    }
  }
}
