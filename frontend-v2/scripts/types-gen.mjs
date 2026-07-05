import { spawnSync } from 'node:child_process';

const input = process.env.VITE_OPENAPI_URL || 'https://ed-finder.app/openapi.json';
const output = 'src/types/api.gen.ts';

const result = spawnSync(
  process.platform === 'win32' ? 'npx.cmd' : 'npx',
  ['openapi-typescript', input, '-o', output],
  { stdio: 'inherit', shell: false },
);

if (result.error) {
  throw result.error;
}

process.exit(result.status ?? 0);
