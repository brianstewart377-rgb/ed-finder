import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { resolve, relative } from 'node:path';

function sources(root: string): string[] {
  return readdirSync(root).flatMap((name) => {
    const path = resolve(root, name);
    return statSync(path).isDirectory() ? sources(path) : /\.tsx?$/.test(name) ? [path] : [];
  });
}

describe('renderer adapter import boundary', () => {
  it('contains every Babylon import in the one renderer adapter directory', () => {
    const root = resolve(process.cwd(), 'src');
    const offenders = sources(root).filter((path) => !path.replaceAll('\\', '/').includes('/features/spatial-runtime/babylon/')).filter((path) => /(?:from\s*|import\s*\(|import\s*)['"](?:@babylonjs|babylonjs)/.test(readFileSync(path, 'utf8')));
    expect(offenders.map((path) => relative(root, path))).toEqual([]);
  });

  it('keeps Babylon names and types out of the public renderer-neutral contract', () => {
    expect(readFileSync(resolve(process.cwd(), 'src/features/spatial-runtime/contracts.ts'), 'utf8')).not.toMatch(/(?:import|from)[^\n]*babylon/i);
  });

  it('does not activate Babylon from the production application entry', () => {
    expect(readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf8')).not.toMatch(/spatial-runtime|spatial-workbench|babylon/i);
  });
});
