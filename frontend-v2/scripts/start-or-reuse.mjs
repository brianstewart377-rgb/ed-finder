#!/usr/bin/env node

import net from 'node:net';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

async function isPortOpen(host, port, timeoutMs = 1000) {
  return await new Promise((resolve) => {
    const socket = new net.Socket();
    let resolved = false;

    const finish = (open) => {
      if (resolved) {
        return;
      }
      resolved = true;
      socket.destroy();
      resolve(open);
    };

    socket.setTimeout(timeoutMs);
    socket.once('connect', () => finish(true));
    socket.once('timeout', () => finish(false));
    socket.once('error', () => finish(false));
    socket.connect(port, host);
  });
}

function withTimeout(ms) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), ms);
  return {
    signal: controller.signal,
    clear: () => clearTimeout(timeout),
  };
}

async function checkLocalHealth() {
  const { signal, clear } = withTimeout(2500);
  try {
    const response = await fetch('http://localhost:3000/api/health', {
      method: 'GET',
      signal,
    });
    return response.ok;
  } catch {
    return false;
  } finally {
    clear();
  }
}

async function main() {
  const inUse = await isPortOpen('127.0.0.1', 3000, 1200);
  if (inUse) {
    const healthy = await checkLocalHealth();
    if (healthy) {
      console.log('Dev server already running on http://localhost:3000 (healthy). Reusing existing process.');
      return;
    }
    console.error(
      'Port 3000 is occupied, but health check failed. Stop the existing process or fix it before starting.'
    );
    process.exit(1);
  }

  const scriptDir = path.dirname(fileURLToPath(import.meta.url));
  const npmExecPath = process.env.npm_execpath;
  if (!npmExecPath) {
    console.error(
      'npm execution context is unavailable. Run `npm install --no-package-lock` in frontend-v2, then rerun `npm run start`.'
    );
    process.exit(1);
  }

  await new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [npmExecPath, 'run', 'dev', '--', '--host', '0.0.0.0', '--port', '3000'], {
      stdio: 'inherit',
      cwd: path.resolve(scriptDir, '..'),
    });

    child.on('error', reject);
    child.on('exit', (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`vite exited with code ${code}`));
      }
    });
  });
}

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`Failed to start dev server: ${message}`);
  process.exit(1);
});
