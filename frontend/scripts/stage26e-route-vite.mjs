import { spawn } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const frontendRoot = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const viteBin = path.join(frontendRoot, 'node_modules', 'vite', 'bin', 'vite.js');
const child = spawn(process.execPath, [viteBin, ...process.argv.slice(2)], {
  cwd: frontendRoot,
  env: {
    ...process.env,
    VITE_STAGE26E_PRODUCTION_MAP: 'enabled',
  },
  stdio: 'inherit',
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => child.kill(signal));
}

child.on('error', (error) => {
  console.error(error);
  process.exitCode = 1;
});
child.on('exit', (code, signal) => {
  process.exitCode = signal ? 1 : code ?? 1;
});
