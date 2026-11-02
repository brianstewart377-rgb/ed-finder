import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse, parseCss, type AST } from 'svelte/compiler';
import { describe, expect, it } from 'vitest';

const sourceRoot = resolve(process.cwd(), 'src');
const appCss = readFileSync(resolve(sourceRoot, 'app.css'), 'utf8');
const stylesheet = parseCss(appCss);

const tokens = {
  '--bg-void': '#080d17',
  '--bg-deep': '#0b1220',
  '--panel': '#121c2e',
  '--panel-raised': '#172539',
  '--panel-sunken': '#0d1524',
  '--panel-gloss':
    'linear-gradient(180deg, rgba(255,255,255,.10), rgba(255,255,255,0) 38%)',
  '--line': '#26405f',
  '--line-strong': '#3a5a84',
  '--line-glow':
    '0 0 0 1px rgba(61,165,255,.18), 0 0 24px rgba(61,165,255,.10)',
  '--text': '#e8eef7',
  '--text-muted': '#9fb0c7',
  '--text-dim': '#6f84a0',
  '--accent': '#ff7a14',
  '--accent-hi': '#ff9a3c',
  '--accent-text': '#1a0d02',
  '--accent-glow': '0 0 22px rgba(255,122,20,.35)',
  '--neon': '#3da5ff',
  '--neon-hi': '#5ec8ff',
  '--neon-soft': 'rgba(61,165,255,.16)',
  '--ok': '#4ade80',
  '--warn': '#e9c46a',
  '--danger': '#f87171',
  '--focus': 'var(--accent)',
  '--radius-sm': '8px',
  '--radius': '14px',
  '--radius-lg': '20px',
  '--radius-pill': '999px',
  '--shadow-panel':
    '0 10px 30px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.06)',
  '--font-hud': "'Saira Semi Condensed', 'Inter', sans-serif",
  '--ease': 'cubic-bezier(.2,.8,.2,1)',
} as const;

const tierColors = {
  '--color-tier-s': '#ff7a14',
  '--color-tier-a': '#7dd3fc',
  '--color-tier-b': '#86d99c',
  '--color-tier-c': '#e9c46a',
  '--color-tier-d': '#a6acb4',
} as const;

function normalize(value: string): string {
  return value
    .replace(/\s+/g, '')
    .replace(/"/g, "'")
    .replace(
      /(?:\b0)?\.(\d+)/g,
      (_, digits: string) => `.${digits.replace(/0+$/, '')}`,
    )
    .toLowerCase();
}

function selector(rule: AST.CSS.Rule, source: string): string {
  return source.slice(rule.prelude.start, rule.prelude.end).trim();
}

const rootDeclarations = new Map<string, string>();
for (const rule of stylesheet.children) {
  if (rule.type !== 'Rule' || selector(rule, appCss) !== ':root') continue;
  for (const declaration of rule.block.children) {
    if (declaration.type === 'Declaration') {
      rootDeclarations.set(declaration.property, declaration.value);
    }
  }
}

function resolveToken(name: string, visited = new Set<string>()): string {
  if (visited.has(name)) throw new Error(`Circular design token: ${name}`);
  const value = rootDeclarations.get(name);
  if (value === undefined) throw new Error(`Missing design token: ${name}`);
  return value.replace(/var\((--[\w-]+)\)/g, (_, reference: string) =>
    resolveToken(reference, new Set([...visited, name])),
  );
}

type CssNode = AST.CSS.Rule | AST.CSS.Atrule | AST.CSS.Declaration;

function hardCodedColors(
  nodes: CssNode[],
  source: string,
  allowTokenBlocks = false,
  context = '',
): string[] {
  return nodes.flatMap((node) => {
    if (node.type === 'Declaration') {
      const colors = node.value.match(
        /#[\da-f]{3,8}\b|\bhsla?\s*\([^)]*\)|\bwhite\b/gi,
      );
      if (!colors) return [];
      return colors.flatMap((color) => {
        const allowedTier =
          node.property in tierColors &&
          normalize(color) ===
            tierColors[node.property as keyof typeof tierColors];
        const allowedSkipLink =
          /(?:^|[\s,])\.skip-link(?:$|[:\s,])/.test(context) &&
          /^(?:white|#fff|#ffffff)$/i.test(color);
        return allowedTier || allowedSkipLink
          ? []
          : [`${context}: ${node.property}: ${node.value}`];
      });
    }
    const nextContext =
      node.type === 'Rule' ? selector(node, source) : `@${node.name}`;
    if (
      allowTokenBlocks &&
      (nextContext === ':root' || nextContext === '@theme')
    ) {
      return [];
    }
    return hardCodedColors(
      node.block?.children ?? [],
      source,
      allowTokenBlocks,
      nextContext,
    );
  });
}

const adoptedComponents = [
  'lib/components/WorkspaceHeader.svelte',
  'routes/+page.svelte',
  'lib/features/explore/ExploreWorkspace.svelte',
  'lib/features/explore/BodyFilters.svelte',
  'lib/features/explore/ArchetypePicker.svelte',
  'lib/features/explore/FinderResultRanking.svelte',
  'lib/components/SystemDetail.svelte',
  'lib/components/GalaxyImpactPanel.svelte',
  'lib/features/explore/WatchlistPanel.svelte',
  'lib/spatial/SpatialCanvas.svelte',
  ...readdirSync(resolve(sourceRoot, 'lib/features/plan'))
    .filter((name) => name.endsWith('.svelte'))
    .map((name) => `lib/features/plan/${name}`),
];

describe('shared design kit', () => {
  it.each(Object.entries(tokens))('defines %s in :root', (name, value) => {
    expect(normalize(rootDeclarations.get(name) ?? '')).toBe(normalize(value));
  });

  it.each([
    ['--color-void', '--bg-void'],
    ['--color-panel', '--panel'],
    ['--color-signal', '--accent'],
    ['--color-cyan', '--neon'],
    ['--muted', '--text-muted'],
  ])('keeps the %s alias connected to %s', (alias, token) => {
    expect(normalize(rootDeclarations.get(alias) ?? '')).toBe(`var(${token})`);
  });

  it('keeps the existing metal surface connected to shared tokens', () => {
    const metal = rootDeclarations.get('--metal');
    expect(metal).toBeDefined();
    expect(metal).toContain('var(--panel');
    expect(() => resolveToken('--metal')).not.toThrow();
  });

  it.each(Object.entries(tierColors))(
    'preserves the existing %s color',
    (name, color) => {
      expect(normalize(resolveToken(name))).toBe(color);
    },
  );

  it.each(adoptedComponents)('%s uses shared colors in styles', (filename) => {
    const source = readFileSync(resolve(sourceRoot, filename), 'utf8');
    // Svelte's parser excludes scripts, template blocks, and inline data, so
    // IDs, literal text, and renderer-owned colors cannot masquerade as CSS.
    const style = parse(source, { modern: true, filename }).css;
    expect(hardCodedColors(style?.children ?? [], source)).toEqual([]);
  });

  it('uses shared colors in the Plan stylesheet', () => {
    const source = readFileSync(
      resolve(sourceRoot, 'lib/features/plan/plan.css'),
      'utf8',
    );
    expect(hardCodedColors(parseCss(source).children, source)).toEqual([]);
  });

  it('uses shared colors outside the global token definitions', () => {
    expect(hardCodedColors(stylesheet.children, appCss, true)).toEqual([]);
  });
});
