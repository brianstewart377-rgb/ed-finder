import { readFile } from 'node:fs/promises';
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
const staticSpaFallbackFile = new URL('./build/200.html', import.meta.url);

export function isStaticSpaRoute(pathname: string): boolean {
  return staticSpaRoutes.some((pattern) => pattern.test(pathname));
}

function staticSpaPreviewFallback(): Plugin {
  let fallbackHtml: Promise<string> | null = null;
  return {
    name: 'ed-finder-static-spa-preview-fallback',
    configurePreviewServer(server) {
      // adapter-static emits build/200.html, but Vite preview does not expose
      // that deployment fallback file through its own static-root mapping.
      // Serve it directly only for known dynamic application namespaces.
      server.middlewares.use((request, response, next) => {
        const method = request.method ?? 'GET';
        if (method !== 'GET' && method !== 'HEAD') return next();

        // Cypress cold visits and other valid navigation clients are not
        // required to advertise Accept: text/html. The exact route match is
        // the safety boundary; backend and unknown paths remain untouched.
        const url = new URL(request.url ?? '/', 'http://127.0.0.1');
        if (!isStaticSpaRoute(url.pathname)) return next();

        fallbackHtml ??= readFile(staticSpaFallbackFile, 'utf8');
        void fallbackHtml
          .then((html) => {
            response.statusCode = 200;
            response.setHeader('Content-Type', 'text/html; charset=utf-8');
            response.setHeader('Cache-Control', 'no-cache');
            response.end(method === 'HEAD' ? undefined : html);
          })
          .catch(next);
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
