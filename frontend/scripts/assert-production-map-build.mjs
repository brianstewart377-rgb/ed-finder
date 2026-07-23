import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const frontendRoot = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const assetPath = path.join(frontendRoot, 'dist', 'stage26e', 'authoritative-regions.json');
const rollbackRequested = process.env.VITE_STAGE26E_PRODUCTION_MAP === 'disabled';

if (rollbackRequested) {
  if (fs.existsSync(assetPath)) {
    throw new Error('Rollback build unexpectedly emitted the Stage 26E region asset');
  }
  console.log('[build-contract] Stage 26E production map disabled; rollback asset omission verified.');
  process.exit(0);
}

if (!fs.existsSync(assetPath)) {
  throw new Error('Production build did not emit the Stage 26E authoritative region asset');
}

const body = fs.readFileSync(assetPath);
const layer = JSON.parse(body.toString('utf8'));
if (body.byteLength > 4 * 1_048_576) {
  throw new Error(`Production region asset exceeds 4 MiB: ${body.byteLength} bytes`);
}
if (!Array.isArray(layer.labels) || layer.labels.length !== 42) {
  throw new Error('Production region asset does not contain exactly 42 labels');
}
if (!Array.isArray(layer.boundaries) || layer.boundaries.length !== 22_595) {
  throw new Error('Production region asset does not contain exactly 22,595 boundaries');
}

console.log(
  `[build-contract] Stage 26E production map enabled: ${body.byteLength} bytes, `
  + `${layer.labels.length} labels, ${layer.boundaries.length} boundaries.`,
);
