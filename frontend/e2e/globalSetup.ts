import { FullConfig } from '@playwright/test';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const API_HOST = process.env.E2E_API_HOST || '127.0.0.1';
const API_PORT = process.env.E2E_API_PORT || '8000';
const API_URL = `http://${API_HOST}:${API_PORT}`;

async function waitForPortRelease(port: number, maxWaitMs: number = 10000): Promise<void> {
  const startTime = Date.now();
  while (Date.now() - startTime < maxWaitMs) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/`, {
        signal: AbortSignal.timeout(200),
      });
      // Port is in use; wait and retry
      await new Promise(resolve => setTimeout(resolve, 200));
    } catch {
      // Port is not in use; success
      return;
    }
  }
  throw new Error(`Port ${port} not released after ${maxWaitMs}ms`);
}

async function waitForBackend(maxRetries = 60, initialDelayMs = 100): Promise<void> {
  let lastError: Error | null = null;

  for (let i = 0; i < maxRetries; i++) {
    try {
      // nosemgrep: typescript.react.security.react-insecure-request.react-insecure-request
      const response = await fetch(`${API_URL}/api/health`, {
        signal: AbortSignal.timeout(2000),
      });
      if (response.ok) {
        const body = await response.json() as Record<string, unknown>;
        // Validate actual health, not just HTTP status
        if (body.status === 'ok' || body.database === 'connected') {
          console.log(`✓ Backend API is ready at ${API_URL}`);
          return;
        }
      }
    } catch (e) {
      lastError = e instanceof Error ? e : new Error(String(e));
    }

    // Exponential backoff: 100ms, 200ms, 400ms, 800ms, 1600ms, then cap at 2s
    const exponentialDelay = Math.min(initialDelayMs * Math.pow(2, i), 2000);

    if (i < maxRetries - 1 && (i + 1) % 10 === 0) {
      console.log(`  Waiting for backend... (${i + 1}/${maxRetries}, next delay: ${exponentialDelay}ms)`);
    }
    await new Promise(resolve => setTimeout(resolve, exponentialDelay));
  }

  // Capture uvicorn logs for diagnosis
  let apiLogs = 'No API logs available';
  try {
    const logFile = process.env.UVICORN_LOG || '/tmp/uvicorn.log';
    const logs = fs.readFileSync(logFile, 'utf-8').split('\n').slice(-20);
    apiLogs = logs.join('\n');
  } catch {
    // Logs not available
  }

  throw new Error(
    `Backend failed to start after ${maxRetries}s at ${API_URL}\n` +
    `Last error: ${lastError?.message}\n` +
    `API logs (last 20 lines):\n${apiLogs}`
  );
}

async function globalSetup(config: FullConfig) {
  const isCI = process.env.CI === 'true' || process.env.GITHUB_ACTIONS === 'true';
  const skipBackend = process.env.EDFINDER_SKIP_E2E_BACKEND === '1';

  if (skipBackend) {
    console.log('ℹ Skipping backend startup (EDFINDER_SKIP_E2E_BACKEND=1)');
    return;
  }

  console.log('Starting E2E backend services...');

  try {
    const repoRoot = path.resolve(__dirname, '../..');
    const composeFile = path.join(repoRoot, 'docker-compose.local.yml');

    // Validate that repo root and compose file exist
    if (!fs.existsSync(composeFile)) {
      throw new Error(
        `docker-compose.local.yml not found at ${composeFile}\n` +
        `Repo root resolved to: ${repoRoot}`
      );
    }

    if (isCI) {
      console.log('ℹ CI environment detected, ensuring clean Docker state...');
      try {
        console.log('  Running: docker compose down --remove-orphans');
        execSync('docker compose -f docker-compose.local.yml down --remove-orphans', {
          cwd: repoRoot,
          stdio: 'inherit',
        });
        console.log('✓ Docker cleanup complete');
      } catch (error) {
        // Only continue if error is "service not found" (no containers to clean)
        if (error instanceof Error && error.message.includes('No such service')) {
          console.log('ℹ No existing containers to clean');
        } else {
          console.error('✗ Docker cleanup failed (proceeding anyway):');
          console.error(error);
        }
      }

      // Skip port wait in CI — fresh runners have no lingering processes
      // If CI exhibits port conflicts, uncomment these:
      // console.log('  Waiting for ports to be released...');
      // try {
      //   await waitForPortRelease(6379, 5000);
      //   await waitForPortRelease(55432, 5000);
      // } catch (error) {
      //   console.warn('⚠ Port release timeout, proceeding anyway:', error);
      // }

      console.log('  Starting Docker services...');
      execSync('docker compose -f docker-compose.local.yml up -d', {
        cwd: repoRoot,
        stdio: 'inherit',
      });
      console.log('✓ Docker services started');

      await waitForBackend();
    } else {
      // Local development: check if services are healthy
      console.log('Checking Docker services...');

      try {
        const healthOutput = execSync(
          'docker compose -f docker-compose.local.yml ps --format "table {{.Service}}\t{{.State}}"',
          { cwd: repoRoot, encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
        );
        const services = healthOutput.split('\n').slice(1).filter(Boolean);
        const allHealthy = services.length > 0 && services.every(line => {
          const parts = line.split(/\s+/);
          const state = parts[1];
          return state === 'running';
        });

        if (allHealthy) {
          console.log('ℹ Docker services already running and healthy');
          await waitForBackend();
          return;
        }
      } catch {
        // Services not running or command failed
      }

      console.log('  Starting Docker services...');
      execSync('docker compose -f docker-compose.local.yml up -d', {
        cwd: repoRoot,
        stdio: 'inherit',
      });
      console.log('✓ Docker services started');

      await waitForBackend();
    }
  } catch (error) {
    console.error('✗ Backend startup failed:', error);
    process.exit(1);
  }
}

async function globalTeardown() {
  const skipBackend = process.env.EDFINDER_SKIP_E2E_BACKEND === '1';
  const isCI = process.env.CI === 'true' || process.env.GITHUB_ACTIONS === 'true';

  if (skipBackend || isCI) {
    return;
  }

  // Optionally stop services after tests (can be disabled with env var)
  if (process.env.EDFINDER_LEAVE_E2E_SERVICES === '1') {
    console.log('ℹ Leaving Docker services running (EDFINDER_LEAVE_E2E_SERVICES=1)');
    return;
  }

  console.log('Stopping E2E backend services...');
  try {
    const repoRoot = path.resolve(__dirname, '../..');
    execSync('docker compose -f docker-compose.local.yml down --volumes', {
      cwd: repoRoot,
      stdio: 'inherit',
    });
    console.log('✓ Docker services stopped and volumes cleaned');
  } catch (error) {
    console.error('✗ Failed to stop services:', error);
  }
}

export { globalSetup as default, globalTeardown };
