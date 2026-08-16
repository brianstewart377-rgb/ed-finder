import { FullConfig } from '@playwright/test';
import { execSync } from 'child_process';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

async function waitForBackend(maxRetries = 30, delayMs = 1000): Promise<void> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch('http://127.0.0.1:8000/api/health', {
        signal: AbortSignal.timeout(2000),
      });
      if (response.ok) {
        console.log('✓ Backend API is ready at 127.0.0.1:8000');
        return;
      }
    } catch (e) {
      // Not ready yet
    }
    if (i < maxRetries - 1) {
      console.log(`  Waiting for backend... (${i + 1}/${maxRetries})`);
    }
    await new Promise(resolve => setTimeout(resolve, delayMs));
  }
  throw new Error('Backend failed to start after 30s');
}

async function globalSetup(config: FullConfig) {
  const isCI = process.env.CI === '1';
  const skipBackend = process.env.EDFINDER_SKIP_E2E_BACKEND === '1';

  if (skipBackend) {
    console.log('ℹ Skipping backend startup (EDFINDER_SKIP_E2E_BACKEND=1)');
    return;
  }

  console.log('Starting E2E backend services...');

  try {
    if (isCI) {
      // In CI, assume docker-compose is already running from the pipeline
      console.log('ℹ CI environment detected, waiting for existing backend...');
      await waitForBackend();
    } else {
      // Local development: start Docker services
      console.log('Starting Docker services (docker-compose.local.yml)...');
      const repoRoot = path.resolve(__dirname, '../..');

      try {
        // Check if services are already running
        const psOutput = execSync('docker compose -f docker-compose.local.yml ps --services --filter "status=running"', {
          cwd: repoRoot,
          encoding: 'utf-8',
          stdio: ['pipe', 'pipe', 'pipe'],
        });
        if (psOutput.trim().length > 0) {
          console.log('ℹ Docker services already running');
        } else {
          throw new Error('No running services');
        }
      } catch {
        // Services not running, start them
        console.log('  Starting Docker services...');
        execSync('docker compose -f docker-compose.local.yml up -d', {
          cwd: repoRoot,
          stdio: 'inherit',
        });
        console.log('✓ Docker services started');
      }

      // Wait for backend to be ready
      await waitForBackend();
    }
  } catch (error) {
    console.error('✗ Backend startup failed:', error);
    process.exit(1);
  }
}

async function globalTeardown() {
  const skipBackend = process.env.EDFINDER_SKIP_E2E_BACKEND === '1';
  const isCI = process.env.CI === '1';

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
    execSync('docker compose -f docker-compose.local.yml down', {
      cwd: repoRoot,
      stdio: 'inherit',
    });
    console.log('✓ Docker services stopped');
  } catch (error) {
    console.error('✗ Failed to stop services:', error);
  }
}

export { globalSetup as default, globalTeardown };
