#!/usr/bin/env node
/**
 * bench-journal-parse.mjs — client-side journal parse benchmark (V3 Task 7).
 *
 * 1. Spawns the deterministic Python generator
 *    (tests/fixtures/journal_v3/generate_large_journal.py) to produce a
 *    ~100k-line synthetic journal under tests/fixtures/journal_v3/generated/
 *    (gitignored).
 * 2. Bundles the REAL client worker parser
 *    (src/lib/journalParsing/journalParser.ts + journalJson.ts, the same code
 *    the browser worker runs) into a temp ESM file via esbuild.
 * 3. Parses the fixture in a Node worker_thread through
 *    parseJournalFilesStreaming (the real worker entry point).
 * 4. Reports lines/s, observations, skipped lines and peak RSS.
 *
 * Usage: node scripts/bench-journal-parse.mjs [--lines 100000] [--seed 20260828]
 */

import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { Worker } from 'node:worker_threads';
import { fileURLToPath } from 'node:url';
import { performance } from 'node:perf_hooks';

const require = createRequire(import.meta.url);
const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = resolve(SCRIPT_DIR, '..');
const REPO_ROOT = resolve(FRONTEND_ROOT, '..');

const args = new Map();
for (let i = 2; i < process.argv.length; i += 1) {
  const key = process.argv[i].replace(/^--/, '');
  args.set(key, process.argv[i + 1]);
}
const LINES = Number(args.get('lines') ?? 100000);
const SEED = Number(args.get('seed') ?? 20260828);
const GENERATED_DIR = join(REPO_ROOT, 'tests', 'fixtures', 'journal_v3', 'generated');
const FIXTURE_PATH = join(GENERATED_DIR, `large_journal_${LINES}.jsonl`);

async function generateFixture() {
  mkdirSync(GENERATED_DIR, { recursive: true });
  const python = join(REPO_ROOT, '.venv', 'Scripts', 'python.exe');
  const start = performance.now();
  await new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(
      python,
      ['-B', 'tests/fixtures/journal_v3/generate_large_journal.py', '--lines', String(LINES), '--seed', String(SEED), '--out', FIXTURE_PATH],
      { cwd: REPO_ROOT, stdio: ['ignore', 'pipe', 'pipe'] },
    );
    let stderr = '';
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.on('error', rejectPromise);
    child.on('exit', (code) => {
      if (code !== 0) {
        rejectPromise(new Error(`generator exited ${code}: ${stderr.slice(0, 500)}`));
      } else {
        resolvePromise();
      }
    });
  });
  return performance.now() - start;
}

async function bundleParser() {
  const esbuild = require('esbuild');
  const entry = [
    'export {',
    '  parseJournalFilesStreaming,',
    '  JOURNAL_PARSER_VERSION,',
    '  SUPPORTED_JOURNAL_EVENTS,',
    `} from ${JSON.stringify(join(FRONTEND_ROOT, 'src', 'lib', 'journalParsing', 'index.ts'))};`,
  ].join('\n');
  const outfile = join(mkdtempSync(join(tmpdir(), 'bench-parser-')), 'parser.bundle.mjs');
  await esbuild.build({
    stdin: { contents: entry, resolveDir: FRONTEND_ROOT, loader: 'ts' },
    bundle: true,
    format: 'esm',
    platform: 'node',
    target: 'node20',
    outfile,
    logLevel: 'silent',
  });
  return outfile;
}

function runParseWorker(bundlePath) {
  const workerScript = join(mkdtempSync(join(tmpdir(), 'bench-worker-')), 'worker.mjs');
  const script = `
import { parentPort, workerData } from 'node:worker_threads';
import { readFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';

const parser = await import(workerData.bundleUrl);
const bytes = readFileSync(workerData.fixturePath);
const file = new File([bytes], 'large_journal.jsonl');
const start = performance.now();
const result = await parser.parseJournalFilesStreaming([{ file }]);
const elapsedMs = performance.now() - start;
parentPort.postMessage({
  lines_read: result.preview.lines_read,
  observations_ready: result.preview.observations_ready,
  skipped_lines: result.preview.skipped_lines,
  event_counts: result.preview.event_counts,
  elapsed_ms: elapsedMs,
  peak_rss_kb: process.resourceUsage().maxRSS,
  parser_version: result.client_manifest.parser_version,
});
`;
  writeFileSync(workerScript, script, 'utf8');

  return new Promise((resolvePromise, rejectPromise) => {
    const worker = new Worker(workerScript, {
      type: 'module',
      workerData: {
        bundleUrl: pathToFileURL(bundlePath).href,
        fixturePath: FIXTURE_PATH,
      },
    });
    worker.once('message', resolvePromise);
    worker.once('error', rejectPromise);
    worker.once('exit', (code) => {
      if (code !== 0) rejectPromise(new Error(`parse worker exited ${code}`));
    });
  });
}

async function main() {
  const rssBefore = process.resourceUsage().maxRSS;
  console.log(`fixture: ${LINES} lines, seed ${SEED} -> ${FIXTURE_PATH}`);
  const generationMs = await generateFixture();
  console.log(`generation: ${(generationMs / 1000).toFixed(2)}s (${Math.round((LINES / generationMs) * 1000).toLocaleString()} lines/s)`);

  const bundleStart = performance.now();
  const bundlePath = await bundleParser();
  console.log(`bundle: real client parser -> ${bundlePath} (${((performance.now() - bundleStart) / 1000).toFixed(2)}s)`);

  const parseStart = performance.now();
  const result = await runParseWorker(bundlePath);
  const parseMs = performance.now() - parseStart;
  const linesPerSecond = result.lines_read / (parseMs / 1000);
  const rssDeltaKb = process.resourceUsage().maxRSS - rssBefore;

  console.log('--- results ---');
  console.log(`parser version : ${result.parser_version}`);
  console.log(`lines read     : ${result.lines_read.toLocaleString()}`);
  console.log(`observations   : ${result.observations_ready.toLocaleString()}`);
  console.log(`skipped lines  : ${result.skipped_lines.toLocaleString()}`);
  console.log(`parse wall     : ${(parseMs / 1000).toFixed(2)}s`);
  console.log(`throughput     : ${Math.round(linesPerSecond).toLocaleString()} lines/s`);
  console.log(`peak RSS worker: ${(result.peak_rss_kb / 1024).toFixed(1)} MiB`);
  console.log(`RSS delta main : ${(rssDeltaKb / 1024).toFixed(1)} MiB`);
  console.log('--- end ---');
}

main().catch((error) => {
  console.error(`bench failed: ${error.message}`);
  process.exit(1);
});
