/// <reference types="vitest" />
import { defineConfig, loadEnv, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const rootDir = fileURLToPath(new URL('.', import.meta.url));
const packageJsonPath = path.resolve(rootDir, 'package.json');
const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf-8')) as { version?: string };
const appVersion = packageJson.version ?? '0.0.0';

function createApiProxyPlugin(proxyTarget: string): Plugin {
  const handler = async (req: any, res: any, next: () => void) => {
    if (!req.url?.startsWith('/api')) {
      next();
      return;
    }

    try {
      const upstreamUrl = new URL(req.url, proxyTarget);
      const headers = new Headers();
      for (const [key, value] of Object.entries(req.headers)) {
        if (!value) continue;
        const lowerKey = key.toLowerCase();
        if (lowerKey === 'host' || lowerKey === 'connection' || lowerKey === 'content-length') {
          continue;
        }
        if (Array.isArray(value)) {
          for (const item of value) {
            headers.append(key, item);
          }
        } else {
          headers.set(key, String(value));
        }
      }

      const bodyChunks: Buffer[] = [];
      if (req.method && !['GET', 'HEAD'].includes(req.method.toUpperCase())) {
        for await (const chunk of req) {
          bodyChunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
        }
      }

      const response = await fetch(upstreamUrl, {
        method: req.method,
        headers,
        body: bodyChunks.length > 0 ? Buffer.concat(bodyChunks) : undefined,
        redirect: 'manual',
      });

      res.statusCode = response.status;
      for (const [key, value] of response.headers.entries()) {
        const lowerKey = key.toLowerCase();
        if (lowerKey === 'content-length' || lowerKey === 'content-encoding' || lowerKey === 'transfer-encoding' || lowerKey === 'connection') {
          continue;
        }
        res.setHeader(key, value);
      }

      const bytes = Buffer.from(await response.arrayBuffer());
      res.setHeader('content-length', String(bytes.length));
      res.end(bytes);
    } catch (error) {
      res.statusCode = 502;
      res.setHeader('content-type', 'application/json');
      res.end(
        JSON.stringify({
          detail: `Local dev proxy could not reach ${proxyTarget}. Check VITE_DEV_API_TARGET and network access.`,
          error: error instanceof Error ? error.message : String(error),
        })
      );
    }
  };

  return {
    name: 'local-dev-api-proxy',
    configureServer(server) {
      server.middlewares.use(handler);
    },
    configurePreviewServer(server) {
      server.middlewares.use(handler);
    },
  };
}

function resolveHmrConfig(loadedEnv: Record<string, string>, runtimeEnv: NodeJS.ProcessEnv) {
  const protocol = loadedEnv.VITE_DEV_HMR_PROTOCOL || runtimeEnv.VITE_DEV_HMR_PROTOCOL;
  const host = loadedEnv.VITE_DEV_HMR_HOST || runtimeEnv.VITE_DEV_HMR_HOST;
  const clientPortRaw = loadedEnv.VITE_DEV_HMR_CLIENT_PORT || runtimeEnv.VITE_DEV_HMR_CLIENT_PORT;
  const clientPort = clientPortRaw ? Number(clientPortRaw) : undefined;

  if (!protocol && !host && clientPort === undefined) {
    return undefined;
  }

  return {
    ...(protocol ? { protocol } : {}),
    ...(host ? { host } : {}),
    ...(Number.isFinite(clientPort) ? { clientPort } : {}),
  };
}

// ────────────────────────────────────────────────────────────────────────────
// Vite config for ed-finder v2 — Emergent preview / dev variant.
//
// Differences from production config:
//   • `base: '/'` — preview serves the v2 React app at the root, not /v2/.
//   • Port 3000 + 0.0.0.0 host so Emergent's ingress can route to it.
//   • PWA plugin disabled (avoids stale SW caching during rapid iteration).
//   • allowedHosts: 'all' so the preview hostname (*.preview.emergentagent.com)
//     is accepted by Vite's HMR / host-check.
//   • /api proxied to local FastAPI on :8001 (the supervisor backend).
// ────────────────────────────────────────────────────────────────────────────
export default defineConfig(({ mode }) => {
  const loadedEnv = loadEnv(mode, rootDir, '');
  const proxyTarget = loadedEnv.VITE_DEV_API_TARGET
    || process.env.VITE_DEV_API_TARGET
    || 'http://127.0.0.1:8001';
  const publicBase = loadedEnv.VITE_PUBLIC_BASE
    || process.env.VITE_PUBLIC_BASE
    || '/';
  const hmr = resolveHmrConfig(loadedEnv, process.env);

  return {
    base: publicBase,
    define: {
      __APP_VERSION__: JSON.stringify(appVersion),
    },
    plugins: [react(), createApiProxyPlugin(proxyTarget)],
    resolve: {
      preserveSymlinks: true,
      alias: {
        '@': path.resolve(rootDir, './src'),
      },
    },
    server: {
      host: '0.0.0.0',
      port: 3000,
      strictPort: true,
      allowedHosts: true,
      ...(hmr ? { hmr } : {}),
    },
    // Preview server (used by Playwright E2E and `yarn preview`) proxies
    // /api the same way the dev server does. Without this, the production
    // bundle served by `vite preview` would 404 every API call.
    preview: {
      host: '0.0.0.0',
      port: 4173,
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
      rollupOptions: {
        output: {
          manualChunks: {
            react: ['react', 'react-dom'],
          },
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      include: ['src/**/*.test.{ts,tsx}'],
    },
  };
});
