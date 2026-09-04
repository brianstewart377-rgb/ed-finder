import svelte from 'eslint-plugin-svelte';
import tseslint from 'typescript-eslint';

import svelteConfig from './svelte.config.js';

export default tseslint.config(
  {
    ignores: [
      '.svelte-kit/',
      'build/',
      'cypress/artifacts/',
      'src/lib/api/generated/',
    ],
  },
  ...tseslint.configs.recommended,
  ...svelte.configs.recommended,
  ...svelte.configs.prettier,
  {
    files: ['**/*.svelte'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
        svelteConfig,
      },
    },
    rules: { 'svelte/no-navigation-without-resolve': 'off' },
  },
  {
    files: ['**/*.svelte.ts'],
    languageOptions: { parser: tseslint.parser },
    rules: { 'svelte/prefer-svelte-reactivity': 'off' },
  },
);
