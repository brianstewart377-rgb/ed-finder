import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import type { Plugin } from 'vite';
import { defineConfig } from 'vitest/config';

const apiTarget = process.env.VITE_DEV_API_TARGET ?? 'http://127.0.0.1:8002';
const backendProxy = {
  '^/api(?:$|[/?])': apiTarget,
  '^/openapi\\.json(?:\\?.*)?$': apiTarget,
  '^/s/\\d+(?:\\?.*)?$': apiTarget,
};

const staticSpaRoutes = [
  /^\/system\/\d+\/?$/,
  /^\/colony-planner(?:\/.*)?\/?$/,
];

export function isStaticSpaRoute(pathname: string): boolean {
  return staticSpaRoutes.some((pattern) => pattern.test(pathname));
}

function staticSpaPreviewFallback(): Plugin {
  return {
    name: 'ed-finder-static-spa-preview-fallback',
    configurePreviewServer(server) {
      // adapter-static emits 200.html, but Vite preview does not infer the
      // deployment host's SPA fallback rule. Rewrite only known dynamic
      // application namespaces before Vite's static middleware runs.
      server.middlewares.use((request, _response, next) => {
        const method = request.method ?? 'GET';
        if (method !== 'GET' && method !== 'HEAD') return next();

        const accept = request.headers.accept ?? '';
        if (!accept.includes('text/html')) return next();

        const url = new URL(request.url ?? '/', 'http://127.0.0.1');
        if (isStaticSpaRoute(url.pathname)) {
          request.url = `/200.html${url.search}`;
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [tailwindcss(), staticSpaPreviewFallback(), sveltekit()],
  resolve: { conditions: ['browser'] },
  server: { proxy: backendProxy },
  preview: { proxy: backendProxy },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
    setupFiles: ['./vitest-setup.ts'],
  },
});
