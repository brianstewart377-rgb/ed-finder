import path from 'node:path';
import os from 'node:os';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const frontendRoot = fileURLToPath(new URL('..', import.meta.url));
const repoRoot = fileURLToPath(new URL('../..', import.meta.url));
const output = path.resolve(frontendRoot, 'src/types/api.gen.ts');
const cliPath = path.resolve(frontendRoot, 'node_modules/openapi-typescript/bin/cli.js');
const apiSrcPath = path.resolve(repoRoot, 'apps/api/src');
const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ed-finder-openapi-'));
const input = path.join(tempDir, 'openapi.json');
const openapiUrl = process.env.VITE_OPENAPI_URL?.trim() || process.env.ED_FINDER_OPENAPI_URL?.trim();

function parseCommand(raw) {
  if (!raw) return null;
  if (fs.existsSync(raw)) return [raw];
  const parts = raw.match(/(?:[^\s"]+|"[^"]*")+/g)?.map((part) => part.replace(/^"|"$/g, '')) ?? [];
  return parts.length > 0 ? parts : [raw];
}

function resolvePython() {
  const envCandidate = parseCommand(process.env.ED_FINDER_PYTHON?.trim());
  const candidates = process.platform === 'win32'
    ? [
        envCandidate,
        [path.resolve(repoRoot, '.venv/Scripts/python.exe')],
        ['py', '-3.12'],
        ['py', '-3.11'],
        ['python'],
      ]
    : [
        envCandidate,
        [path.resolve(repoRoot, '.venv/bin/python')],
        ['python3.12'],
        ['python3.11'],
        ['python3'],
        ['python'],
      ];

  for (const candidate of candidates) {
    if (!candidate) continue;
    const [command, ...prefixArgs] = candidate;
    const probe = spawnSync(
      command,
      [...prefixArgs, '-c', 'import asyncpg'],
      { stdio: 'ignore', shell: false, cwd: repoRoot },
    );
    if (!probe.error && probe.status === 0) return candidate;
  }

  throw new Error(
    'No usable Python interpreter found for local OpenAPI generation. Install Python 3.12/3.11 and ensure asyncpg can be imported, or set ED_FINDER_PYTHON to a compatible interpreter.',
  );
}

if (openapiUrl) {
  const schemaFetchResult = spawnSync(
    process.execPath,
    [cliPath, openapiUrl, '-o', output],
    { stdio: 'inherit', shell: false },
  );

  if (schemaFetchResult.error) {
    throw schemaFetchResult.error;
  }

  process.exit(schemaFetchResult.status ?? 0);
}

const pythonCommand = resolvePython();
const [python, ...pythonArgs] = pythonCommand;
const pythonCode = [
  'import json, sys',
  `sys.path.insert(0, r"${apiSrcPath.replace(/\\/g, '\\\\')}")`,
  'from main import app',
  'with open(sys.argv[1], "w", encoding="utf-8") as handle:',
  '    json.dump(app.openapi(), handle)',
].join('\n');

const schemaResult = spawnSync(
  python,
  [...pythonArgs, '-B', '-c', pythonCode, input],
  { stdio: 'inherit', shell: false, cwd: repoRoot },
);

if (schemaResult.error) {
  throw schemaResult.error;
}

if ((schemaResult.status ?? 0) !== 0) {
  process.exit(schemaResult.status ?? 1);
}

const result = spawnSync(
  process.execPath,
  [cliPath, input, '-o', output],
  { stdio: 'inherit', shell: false },
);

if (result.error) {
  throw result.error;
}

try {
  fs.rmSync(tempDir, { recursive: true, force: true });
} catch {
  // Best effort cleanup only.
}

process.exit(result.status ?? 0);
