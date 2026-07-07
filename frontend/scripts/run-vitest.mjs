import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { parseCLI, startVitest } from 'vitest/node';

const frontendRoot = fileURLToPath(new URL('..', import.meta.url));
const packageJsonPath = path.resolve(frontendRoot, 'package.json');
const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf-8'));
const appVersion = packageJson.version ?? '0.0.0';
const modeArg = process.argv[2] === 'watch' ? 'watch' : 'run';
const argv = process.argv.slice(modeArg === 'watch' || process.argv[2] === 'run' ? 3 : 2);
const { filter, options } = parseCLI(['vitest', ...argv]);

const vitest = await startVitest(
  'test',
  filter,
  {
    ...options,
    root: frontendRoot,
    config: false,
    run: modeArg === 'run',
    watch: modeArg === 'watch',
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.{ts,tsx}'],
  },
  {
    root: frontendRoot,
    define: {
      __APP_VERSION__: JSON.stringify(appVersion),
    },
    plugins: [react()],
    resolve: {
      preserveSymlinks: true,
      alias: {
        '@': path.resolve(frontendRoot, './src'),
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      include: ['src/**/*.test.{ts,tsx}'],
    },
  },
);

if (!vitest) {
  process.exitCode = 1;
}
