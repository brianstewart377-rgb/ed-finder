import type { FullConfig } from '@playwright/test';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '../..');
const composeFile = path.join(repoRoot, 'docker-compose.local.yml');

type BackendMode = 'external' | 'compose';

function resolveApiUrl(): string {
  // Explicit E2E host/port wins for ordinary CI, which boots its API on :8002.
  if (process.env.E2E_API_HOST || process.env.E2E_API_PORT) {
    const host = process.env.E2E_API_HOST || '127.0.0.1';
    const port = process.env.E2E_API_PORT || '8000';
    return `http://${host}:${port}`;
  }

  // Review Lab owns an isolated API on :8001 and already passes that exact
  // origin to Vite as VITE_DEV_API_TARGET. Reuse the same target for backend
  // readiness instead of falling back to the unrelated normal API on :8000.
  const viteApiTarget = process.env.VITE_DEV_API_TARGET?.trim();
  if (viteApiTarget) {
    const parsed = new URL(viteApiTarget);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      throw new Error(
        `Invalid VITE_DEV_API_TARGET=${JSON.stringify(viteApiTarget)}; `
        + 'expected an http(s) URL.',
      );
    }
    return parsed.origin;
  }

  return 'http://127.0.0.1:8000';
}

const API_URL = resolveApiUrl();

function sleep(delayMs: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, delayMs));
}

function resolveBackendMode(): BackendMode {
  const explicitMode = process.env.EDFINDER_E2E_BACKEND_MODE?.trim().toLowerCase();
  if (explicitMode) {
    if (explicitMode !== 'external' && explicitMode !== 'compose') {
      throw new Error(
        `Invalid EDFINDER_E2E_BACKEND_MODE=${JSON.stringify(explicitMode)}; `
        + 'expected "external" or "compose".',
      );
    }
    return explicitMode;
  }

  // Backwards-compatible markers for callers that already own the backend.
  if (
    process.env.EDFINDER_SKIP_E2E_BACKEND === '1'
    || process.env.EDFINDER_REVIEW_LAB_RUN === '1'
  ) {
    return 'external';
  }

  const isCI = process.env.CI === 'true' || process.env.GITHUB_ACTIONS === 'true';
  if (isCI && process.env.E2E_API_PORT) {
    console.warn(
      '⚠ CI E2E backend ownership inferred from E2E_API_PORT. '
      + 'Set EDFINDER_E2E_BACKEND_MODE=external explicitly in the caller.',
    );
    return 'external';
  }

  return 'compose';
}

function readApiLogTail(): string {
  try {
    const logFile = process.env.UVICORN_LOG || '/tmp/uvicorn.log';
    return fs.readFileSync(logFile, 'utf-8').split('\n').slice(-30).join('\n');
  } catch {
    return 'No API logs available';
  }
}

async function waitForBackend(timeoutMs = 60_000): Promise<void> {
  const startedAt = Date.now();
  const deadline = startedAt + timeoutMs;
  let attempt = 0;
  let lastError: Error | null = null;
  let lastStatus: number | null = null;
  let lastBody = '';

  while (Date.now() < deadline) {
    attempt += 1;
    try {
      // nosemgrep: typescript.react.security.react-insecure-request.react-insecure-request
      const response = await fetch(`${API_URL}/api/health`, {
        signal: AbortSignal.timeout(2_000),
      });
      lastStatus = response.status;
      lastBody = await response.text();

      if (response.ok) {
        try {
          const body = JSON.parse(lastBody) as Record<string, unknown>;
          if (body.status === 'ok' || body.database === 'connected') {
            console.log(`✓ Backend API is ready at ${API_URL}`);
            return;
          }
        } catch (error) {
          lastError = error instanceof Error ? error : new Error(String(error));
        }
      }
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
    }

    const elapsedMs = Date.now() - startedAt;
    if (elapsedMs >= timeoutMs) {
      break;
    }

    const delayMs = Math.min(100 * (2 ** Math.min(attempt - 1, 5)), 2_000);
    if (attempt === 1 || attempt % 5 === 0) {
      console.log(
        `  Waiting for backend at ${API_URL} `
        + `(elapsed ${(elapsedMs / 1000).toFixed(1)}s, next delay ${delayMs}ms)`,
      );
    }
    await sleep(Math.min(delayMs, Math.max(0, deadline - Date.now())));
  }

  throw new Error(
    `Backend did not become ready within ${timeoutMs}ms at ${API_URL}\n`
    + `Last HTTP status: ${lastStatus ?? 'none'}\n`
    + `Last response body: ${lastBody || 'none'}\n`
    + `Last error: ${lastError?.message ?? 'none'}\n`
    + `API logs (last 30 lines):\n${readApiLogTail()}`,
  );
}

function runningComposeServices(): Set<string> {
  try {
    const output = execSync(
      'docker compose -f docker-compose.local.yml ps --services --status running',
      {
        cwd: repoRoot,
        encoding: 'utf-8',
        stdio: ['ignore', 'pipe', 'pipe'],
      },
    );
    return new Set(output.split(/\r?\n/).map((line) => line.trim()).filter(Boolean));
  } catch {
    return new Set();
  }
}

function startComposeDependencies(): void {
  if (!fs.existsSync(composeFile)) {
    throw new Error(
      `docker-compose.local.yml not found at ${composeFile}\n`
      + `Repo root resolved to: ${repoRoot}`,
    );
  }

  console.log('  Starting Docker dependencies owned by the E2E harness...');
  execSync('docker compose -f docker-compose.local.yml up -d', {
    cwd: repoRoot,
    stdio: 'inherit',
  });
  console.log('✓ Docker dependencies started');
}

function stopOwnedComposeDependencies(): void {
  if (process.env.EDFINDER_LEAVE_E2E_SERVICES === '1') {
    console.log('ℹ Leaving E2E-owned Docker services running (EDFINDER_LEAVE_E2E_SERVICES=1)');
    return;
  }

  console.log('Stopping E2E-owned Docker dependencies...');
  try {
    // Deliberately preserve volumes: docker-compose.local.yml is also the local
    // development stack and a test run must never destroy a developer's data.
    execSync('docker compose -f docker-compose.local.yml down --remove-orphans', {
      cwd: repoRoot,
      stdio: 'inherit',
    });
    console.log('✓ E2E-owned Docker dependencies stopped');
  } catch (error) {
    console.error('✗ Failed to stop E2E-owned Docker dependencies:', error);
  }
}

async function globalSetup(_config: FullConfig) {
  const backendMode = resolveBackendMode();

  if (backendMode === 'external') {
    console.log(`ℹ E2E backend is externally managed; verifying readiness at ${API_URL}`);
    await waitForBackend();
    return;
  }

  console.log('Checking E2E Docker dependencies...');
  const runningServices = runningComposeServices();
  const dependenciesAlreadyRunning = runningServices.has('postgres') && runningServices.has('redis');

  if (dependenciesAlreadyRunning) {
    console.log('ℹ Postgres and Redis are already running; the harness will not claim ownership');
    await waitForBackend();
    return;
  }

  let ownsComposeDependencies = false;
  try {
    startComposeDependencies();
    ownsComposeDependencies = true;
    await waitForBackend();
  } catch (error) {
    if (ownsComposeDependencies) {
      stopOwnedComposeDependencies();
    }
    throw error;
  }

  // Playwright invokes a function returned from globalSetup as global teardown.
  // Only stop services that this invocation actually started.
  return async () => {
    stopOwnedComposeDependencies();
  };
}

export { globalSetup as default };
