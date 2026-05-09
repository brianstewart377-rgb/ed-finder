// eslint.config.js — flat config (ESLint v9+).
//
// Replaces the implicit-legacy .eslintrc.* the repo had been running
// without since the v8→v9 bump in package.json (which made `yarn lint`
// fail with "ESLint couldn't find an eslint.config.(js|mjs|cjs) file").
//
// What's enabled:
//   * @eslint/js     — ESLint's recommended core rules
//   * typescript-eslint v8 — the unified TS plugin (recommended preset).
//                            Type-aware linting is OFF for now (it
//                            requires `parserOptions.project`, which
//                            doubles the lint runtime); the recommended
//                            preset still catches the high-value bugs.
//   * react-hooks    — rules-of-hooks + exhaustive-deps. The hook
//                      bug class would have caught the audit's
//                      `useEffect` regression in PR review.
//   * react-refresh  — Vite HMR safety net.
//
// What's intentionally *not* enabled:
//   * `eslint-plugin-react/all` — the legacy preset is noisy with React
//     19 / the new JSX transform. Added rule-by-rule above instead.
//   * Type-aware `recommendedTypeChecked` — see note above.

import js                 from '@eslint/js';
import tseslint           from 'typescript-eslint';
import reactHooks         from 'eslint-plugin-react-hooks';
import reactRefresh       from 'eslint-plugin-react-refresh';
import globals            from 'globals';

export default tseslint.config(
  // Globally ignore build artefacts + generated code so it never
  // triggers manual lint failures (the OpenAPI types-drift check
  // already pins the generated file).
  {
    ignores: [
      'dist/**',
      'node_modules/**',
      'src/types/api.gen.ts',
      'playwright-report/**',
      'test-results/**',
      'coverage/**',
      '**/*.d.ts',
    ],
  },

  // Base recommendations.
  js.configs.recommended,
  ...tseslint.configs.recommended,

  // Application source — TS / TSX with React-specific rules.
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion:  2022,
      sourceType:   'module',
      globals:      { ...globals.browser, ...globals.es2021 },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      'react-hooks':   reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      // React-hooks rules — non-negotiable correctness.
      ...reactHooks.configs.recommended.rules,

      // Vite HMR boundary check — only export components from a
      // component file. Catches a class of HMR-breakage bugs early.
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],

      // Style relaxations — the audit-era code uses these patterns
      // intentionally. Tightening them would be a separate PR with
      // its own diff to review.
      '@typescript-eslint/no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-empty-object-type': 'off',
      // The audit's `extra='allow'` row models intentionally hand
      // `Record<string, unknown>`-shaped objects to React; banning
      // ts-comment escape hatches there would be busy-work.
      '@typescript-eslint/ban-ts-comment': [
        'warn',
        { 'ts-expect-error': false, 'ts-ignore': 'allow-with-description' },
      ],
    },
  },

  // Vite + tooling configs run in Node and can use require/process.
  {
    files: ['*.config.{js,ts,mjs,cjs}', 'vite.config.ts'],
    languageOptions: {
      globals: { ...globals.node },
    },
  },
);
