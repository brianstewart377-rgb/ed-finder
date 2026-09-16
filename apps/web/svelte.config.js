import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

const buildSha = process.env.VITE_BUILD_SHA;
if (buildSha !== undefined && !/^[0-9a-f]{40}$/.test(buildSha)) {
  throw new Error(
    'VITE_BUILD_SHA must be exactly 40 lowercase hexadecimal characters',
  );
}

const buildIdentity = buildSha ?? 'development';

// Expose the build identity to app.html as %sveltekit.env.PUBLIC_BUILD_SHA%.
// ssr is disabled, so a component <svelte:head> never reaches the no-JS HTML
// that the production deploy smoke fetches; the release identity meta tag it
// requires (name="edfinder-build-sha") must be baked into the static template,
// and SvelteKit only substitutes PUBLIC_-prefixed env vars there. Deriving it
// here keeps a single source of truth (VITE_BUILD_SHA) with no extra CI wiring.
process.env.PUBLIC_BUILD_SHA = buildIdentity;

export default {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({ fallback: '200.html' }),
    // SvelteKit otherwise defaults this file-content identity to Date.now(),
    // making two builds of the same reviewed source produce different output.
    version: { name: buildIdentity },
  },
};
