#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import { execSync } from 'node:child_process';

const APP_ROOT = process.cwd();
const REPO_ROOT = path.resolve(APP_ROOT, '..');
const args = new Set(process.argv.slice(2));
const strictMode = args.has('--strict');
const DEFAULT_CANONICAL_COMPARE_REF = 'origin/work/r1-canonical-body-evidence';

const warnings = [];
const failures = [];

function runGit(argsText, allowFailure = false) {
  try {
    return execSync(`git ${argsText}`, {
      cwd: REPO_ROOT,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
  } catch (error) {
    if (allowFailure) {
      return null;
    }
    const message =
      error instanceof Error ? error.message : `Unknown git error while running: git ${argsText}`;
    throw new Error(message);
  }
}

function parseEnvFile(filePath) {
  if (!fs.existsSync(filePath)) {
    return {};
  }

  const contents = fs.readFileSync(filePath, 'utf8');
  const result = {};

  for (const rawLine of contents.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) {
      continue;
    }

    const delimiterIndex = line.indexOf('=');
    if (delimiterIndex === -1) {
      continue;
    }

    const key = line.slice(0, delimiterIndex).trim();
    let value = line.slice(delimiterIndex + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    result[key] = value;
  }

  return result;
}

function resolveApiTarget() {
  if (process.env.VITE_DEV_API_TARGET) {
    return {
      target: process.env.VITE_DEV_API_TARGET,
      source: 'process.env.VITE_DEV_API_TARGET',
    };
  }

  const envLocalPath = path.join(APP_ROOT, '.env.local');
  const envPath = path.join(APP_ROOT, '.env');

  const envLocal = parseEnvFile(envLocalPath);
  if (envLocal.VITE_DEV_API_TARGET) {
    return {
      target: envLocal.VITE_DEV_API_TARGET,
      source: '.env.local',
    };
  }

  const envFile = parseEnvFile(envPath);
  if (envFile.VITE_DEV_API_TARGET) {
    return {
      target: envFile.VITE_DEV_API_TARGET,
      source: '.env',
    };
  }

  return {
    target: 'http://127.0.0.1:8001',
    source: 'vite fallback default',
  };
}

function resolveCompareRef() {
  const override = process.env.DEV_DOCTOR_COMPARE_REF?.trim();
  if (override) {
    return {
      ref: override,
      source: 'process.env.DEV_DOCTOR_COMPARE_REF',
    };
  }

  return {
    ref: DEFAULT_CANONICAL_COMPARE_REF,
    source: 'default canonical branch',
  };
}

function withTimeout(ms) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), ms);
  return {
    signal: controller.signal,
    clear: () => clearTimeout(timeout),
  };
}

async function isPortOpen(host, port, timeoutMs = 1000) {
  return await new Promise((resolve) => {
    const socket = new net.Socket();
    let resolved = false;

    const finish = (isOpen) => {
      if (resolved) {
        return;
      }
      resolved = true;
      socket.destroy();
      resolve(isOpen);
    };

    socket.setTimeout(timeoutMs);
    socket.once('connect', () => finish(true));
    socket.once('timeout', () => finish(false));
    socket.once('error', () => finish(false));
    socket.connect(port, host);
  });
}

function buildHealthUrl(rawTarget) {
  try {
    const url = new URL(rawTarget);
    const normalizedPath = url.pathname.endsWith('/')
      ? url.pathname.slice(0, -1)
      : url.pathname;
    const healthPath = normalizedPath.endsWith('/api')
      ? `${normalizedPath}/health`
      : `${normalizedPath}/api/health`;
    url.pathname = healthPath;
    url.search = '';
    url.hash = '';
    return url.toString();
  } catch {
    return null;
  }
}

async function fetchJson(url, timeoutMs = 3000) {
  const { signal, clear } = withTimeout(timeoutMs);
  try {
    const response = await fetch(url, { method: 'GET', signal });
    const text = await response.text();
    let parsedBody = null;
    try {
      parsedBody = text ? JSON.parse(text) : null;
    } catch {
      parsedBody = null;
    }
    return {
      ok: response.ok,
      status: response.status,
      body: parsedBody,
      text,
    };
  } catch (error) {
    return {
      ok: false,
      status: 0,
      body: null,
      text: error instanceof Error ? error.message : String(error),
    };
  } finally {
    clear();
  }
}

function printSection(title) {
  console.log('');
  console.log(title);
}

function printResult(status, message) {
  console.log(`${status} ${message}`);
}

async function main() {
  console.log('ED-Finder Frontend Dev Doctor');
  console.log('Reminder: run this after pull, after env changes, and before UI verification.');

  printSection('Git state');
  const branch = runGit('rev-parse --abbrev-ref HEAD', true) || '(unknown)';
  const commit = runGit('rev-parse --short HEAD', true) || '(unknown)';
  printResult('[ok]', `branch=${branch} commit=${commit}`);
  const { ref: compareRef, source: compareRefSource } = resolveCompareRef();
  printResult('[ok]', `compare ref=${compareRef} (source: ${compareRefSource})`);

  const trackedChanges = runGit('status --porcelain --untracked-files=no', true) || '';
  if (trackedChanges) {
    warnings.push('Tracked local changes exist. You may be testing a non-merged state.');
    printResult('[warn]', 'tracked local changes detected');
  } else {
    printResult('[ok]', 'tracked files clean');
  }

  const untrackedChanges = (runGit('status --porcelain --untracked-files=all', true) || '')
    .split(/\r?\n/)
    .filter((line) => line.startsWith('?? '))
    .map((line) => line.slice(3).trim())
    .filter((entry) => entry && !entry.startsWith('.codex-context/'));
  if (untrackedChanges.length > 0) {
    warnings.push('Untracked files (outside .codex-context) exist. Confirm they are intentional.');
    printResult('[warn]', `untracked files: ${untrackedChanges.slice(0, 3).join(', ')}`);
  } else {
    printResult('[ok]', 'no untracked files outside .codex-context/');
  }

  const fetched = runGit('fetch --quiet origin', true);
  if (fetched !== null && branch !== '(unknown)') {
    const compareRefExists = runGit(`rev-parse --verify ${compareRef}`, true);
    const aheadBehindRaw = compareRefExists
      ? runGit(`rev-list --left-right --count HEAD...${compareRef}`, true) || ''
      : '';
    if (!compareRefExists) {
      warnings.push(`Unable to verify comparison reference ${compareRef}.`);
      printResult('[warn]', `unable to verify comparison reference ${compareRef}`);
    } else if (aheadBehindRaw) {
      const [aheadText, behindText] = aheadBehindRaw.split(/\s+/);
      const ahead = Number(aheadText || '0');
      const behind = Number(behindText || '0');
      if (ahead > 0 && behind > 0) {
        warnings.push(`Branch diverged from ${compareRef}.`);
        printResult('[warn]', `branch diverged (ahead ${ahead}, behind ${behind})`);
      } else if (behind > 0) {
        warnings.push(`Local branch is behind ${compareRef} by ${behind} commit(s).`);
        printResult('[warn]', `behind ${compareRef} by ${behind}`);
      } else if (ahead > 0) {
        warnings.push(`Local branch is ahead of ${compareRef} by ${ahead} commit(s).`);
        printResult('[warn]', `ahead of ${compareRef} by ${ahead}`);
      } else {
        printResult('[ok]', `in sync with ${compareRef}`);
      }
    } else {
      printResult('[warn]', `unable to compare against ${compareRef}`);
    }
  } else {
    printResult('[warn]', 'unable to fetch origin for sync check');
  }

  printSection('API target');
  const { target, source } = resolveApiTarget();
  printResult('[ok]', `VITE_DEV_API_TARGET=${target} (source: ${source})`);
  if (target === 'http://127.0.0.1:8001') {
    warnings.push(
      'Using local default API target. If local backend is not running, frontend requests will fail.'
    );
    printResult('[warn]', 'default local target in use');
  }

  const targetHealthUrl = buildHealthUrl(target);
  if (targetHealthUrl) {
    const targetHealth = await fetchJson(targetHealthUrl, 4000);
    if (targetHealth.ok) {
      const statusValue =
        targetHealth.body && typeof targetHealth.body === 'object' && 'status' in targetHealth.body
          ? String(targetHealth.body.status)
          : '(no status field)';
      printResult('[ok]', `target health ${targetHealth.status} status=${statusValue}`);
    } else {
      warnings.push(`Unable to confirm target health at ${targetHealthUrl}.`);
      printResult('[warn]', `target health check failed (${targetHealth.status || 'network error'})`);
    }
  } else {
    warnings.push(`Invalid VITE_DEV_API_TARGET URL: ${target}`);
    printResult('[warn]', 'target is not a valid URL');
  }

  printSection('Local dev server');
  const portInUse = await isPortOpen('127.0.0.1', 3000, 1200);
  if (!portInUse) {
    printResult('[ok]', 'port 3000 is free');
  } else {
    printResult('[ok]', 'port 3000 already in use');
    const localHealth = await fetchJson('http://localhost:3000/api/health', 2500);
    if (localHealth.ok) {
      const statusValue =
        localHealth.body && typeof localHealth.body === 'object' && 'status' in localHealth.body
          ? String(localHealth.body.status)
          : '(no status field)';
      printResult('[ok]', `localhost proxy health ${localHealth.status} status=${statusValue}`);
    } else {
      warnings.push('Port 3000 is occupied but /api/health is not reachable on localhost:3000.');
      printResult('[warn]', 'existing :3000 process does not look healthy');
    }
  }

  printSection('Summary');
  if (failures.length === 0 && warnings.length === 0) {
    printResult('[ok]', 'all checks passed');
  } else {
    for (const warning of warnings) {
      printResult('[warn]', warning);
    }
    for (const failure of failures) {
      printResult('[fail]', failure);
    }
  }

  const syncBranch = compareRef.startsWith('origin/') ? compareRef.slice('origin/'.length) : compareRef;
  console.log('');
  console.log(
    `If warnings appear, run: git pull --ff-only origin ${syncBranch}, verify .env.local, restart dev server, then rerun npm run dev:doctor:strict`
  );

  if (strictMode && (warnings.length > 0 || failures.length > 0)) {
    process.exit(1);
  }
}

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`[fail] dev-doctor crashed: ${message}`);
  process.exit(1);
});
