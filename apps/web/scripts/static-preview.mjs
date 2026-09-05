import { createReadStream } from 'node:fs';
import { readdir, realpath, stat } from 'node:fs/promises';
import {
  createServer as createHttpServer,
  request as createHttpRequest,
} from 'node:http';
import { request as createHttpsRequest } from 'node:https';
import { isIP } from 'node:net';
import { extname, isAbsolute, relative, resolve, sep } from 'node:path';
import { pipeline } from 'node:stream';
import { fileURLToPath, pathToFileURL } from 'node:url';

const DEFAULT_BUILD_ROOT = fileURLToPath(new URL('../build/', import.meta.url));
const DEFAULT_HOST = '127.0.0.1';
const DEFAULT_PORT = 4173;
const PROXY_TIMEOUT_MS = 30_000;

const BACKEND_ROUTES = [
  /^\/api(?:\/|$)/u,
  /^\/openapi\.json$/u,
  /^\/s\/[0-9]+$/u,
];

const HOP_BY_HOP_HEADERS = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'proxy-connection',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
]);

const SPOOFABLE_FORWARDING_HEADERS = new Set([
  'forwarded',
  'x-forwarded-for',
  'x-forwarded-host',
  'x-forwarded-port',
  'x-forwarded-proto',
]);

const CONTENT_TYPES = new Map([
  ['.avif', 'image/avif'],
  ['.css', 'text/css; charset=utf-8'],
  ['.gif', 'image/gif'],
  ['.htm', 'text/html; charset=utf-8'],
  ['.html', 'text/html; charset=utf-8'],
  ['.ico', 'image/x-icon'],
  ['.jpeg', 'image/jpeg'],
  ['.jpg', 'image/jpeg'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.map', 'application/json; charset=utf-8'],
  ['.mjs', 'text/javascript; charset=utf-8'],
  ['.ogg', 'audio/ogg'],
  ['.otf', 'font/otf'],
  ['.png', 'image/png'],
  ['.svg', 'image/svg+xml'],
  ['.txt', 'text/plain; charset=utf-8'],
  ['.wasm', 'application/wasm'],
  ['.webmanifest', 'application/manifest+json; charset=utf-8'],
  ['.webp', 'image/webp'],
  ['.woff', 'font/woff'],
  ['.woff2', 'font/woff2'],
  ['.xml', 'application/xml; charset=utf-8'],
]);

export class UnsafeRequestTargetError extends Error {}

function decodeUrlComponent(value, description) {
  try {
    return decodeURIComponent(value);
  } catch (error) {
    throw new UnsafeRequestTargetError(
      `Malformed percent encoding in ${description}`,
      { cause: error },
    );
  }
}

function validateDecodedPathname(pathname) {
  if (!pathname.startsWith('/')) {
    throw new UnsafeRequestTargetError(
      'Only origin-form request paths are accepted',
    );
  }
  if (pathname.includes('\0')) {
    throw new UnsafeRequestTargetError(
      'Null bytes are not accepted in request paths',
    );
  }
  if (pathname.includes('\\')) {
    throw new UnsafeRequestTargetError(
      'Backslashes are not accepted in request paths',
    );
  }
  if (
    pathname.split('/').some((segment) => segment === '.' || segment === '..')
  ) {
    throw new UnsafeRequestTargetError(
      'Traversal segments are not accepted in request paths',
    );
  }
}

export function parseRequestTarget(requestTarget) {
  if (typeof requestTarget !== 'string' || requestTarget.length === 0) {
    throw new UnsafeRequestTargetError('A request target is required');
  }
  if (requestTarget.includes('#')) {
    throw new UnsafeRequestTargetError(
      'Fragments are not accepted in HTTP request targets',
    );
  }

  const queryIndex = requestTarget.indexOf('?');
  const rawPathname =
    queryIndex === -1 ? requestTarget : requestTarget.slice(0, queryIndex);
  const search = queryIndex === -1 ? '' : requestTarget.slice(queryIndex);

  if (rawPathname.includes('\\') || rawPathname.includes('\0')) {
    throw new UnsafeRequestTargetError('Unsafe characters in request path');
  }

  const pathname = decodeUrlComponent(rawPathname, 'request path');
  // Validate the query encoding even though it is deliberately excluded from
  // filesystem resolution. The original bytes are retained for proxying.
  if (search) decodeUrlComponent(search.slice(1), 'query string');
  validateDecodedPathname(pathname);

  return { pathname, rawPathname, search };
}

export function classifyRoute(rawPathname) {
  const pathname = decodeUrlComponent(rawPathname, 'request path');
  validateDecodedPathname(pathname);
  return BACKEND_ROUTES.some((pattern) => pattern.test(rawPathname))
    ? 'backend'
    : 'frontend';
}

function isWithinRoot(root, candidate) {
  const pathFromRoot = relative(root, candidate);
  return (
    pathFromRoot === '' ||
    (!pathFromRoot.startsWith(`..${sep}`) &&
      pathFromRoot !== '..' &&
      !isAbsolute(pathFromRoot))
  );
}

function contentHeaders(filePath, metadata, fallback) {
  let typePath = filePath;
  const headers = {
    'Content-Length': String(metadata.size),
    'Last-Modified': metadata.mtime.toUTCString(),
    'X-Content-Type-Options': 'nosniff',
  };

  if (filePath.endsWith('.br')) {
    headers['Content-Encoding'] = 'br';
    typePath = filePath.slice(0, -3);
  } else if (filePath.endsWith('.gz')) {
    headers['Content-Encoding'] = 'gzip';
    typePath = filePath.slice(0, -3);
  }

  const extension = extname(typePath).toLowerCase();
  headers['Content-Type'] =
    CONTENT_TYPES.get(extension) ?? 'application/octet-stream';
  headers['Cache-Control'] =
    fallback || extension === '.html'
      ? 'no-cache'
      : 'public, max-age=0, must-revalidate';
  return headers;
}

async function indexStaticFiles(buildRoot) {
  const files = new Map();

  async function visit(directory, pathname) {
    const entries = await readdir(directory, { withFileTypes: true });
    for (const entry of entries) {
      const entryPath = resolve(directory, entry.name);
      if (!isWithinRoot(buildRoot, entryPath)) {
        throw new Error('Static build entry escaped the build root');
      }

      const entryPathname =
        pathname === '/' ? `/${entry.name}` : `${pathname}/${entry.name}`;
      if (entry.isDirectory()) {
        await visit(entryPath, entryPathname);
        continue;
      }
      // Static build output is immutable and consists of regular files. Ignore
      // symlinks and other special entries so a request can select only a file
      // which was proved to be inside the canonical build root at startup.
      if (!entry.isFile()) continue;

      const canonicalPath = await realpath(entryPath);
      if (!isWithinRoot(buildRoot, canonicalPath)) {
        throw new Error('Static build file escaped the build root');
      }
      const metadata = await stat(canonicalPath);
      if (!metadata.isFile()) continue;

      const file = { filePath: canonicalPath, metadata };
      files.set(entryPathname, file);
      if (entry.name === 'index.html') {
        files.set(pathname, file);
        if (pathname !== '/') files.set(`${pathname}/`, file);
      }
    }
  }

  await visit(buildRoot, '/');
  return files;
}

function normalizeStaticLookupPathname(pathname) {
  validateDecodedPathname(pathname);
  return pathname.replace(/\/{2,}/gu, '/');
}

function sendText(request, response, statusCode, message, extraHeaders = {}) {
  const body = Buffer.from(`${message}\n`, 'utf8');
  response.writeHead(statusCode, {
    'Cache-Control': 'no-store',
    'Content-Length': String(body.length),
    'Content-Type': 'text/plain; charset=utf-8',
    'X-Content-Type-Options': 'nosniff',
    ...extraHeaders,
  });
  response.end(request.method === 'HEAD' ? undefined : body);
}

function serveFile(request, response, file, fallback) {
  response.writeHead(
    200,
    contentHeaders(file.filePath, file.metadata, fallback),
  );
  if (request.method === 'HEAD') {
    response.end();
    return;
  }

  const stream = createReadStream(file.filePath);
  pipeline(stream, response, (error) => {
    if (error && !response.destroyed) response.destroy(error);
  });
}

function connectionHeaderNames(headers) {
  const connection = headers.connection;
  if (!connection) return [];
  const values = Array.isArray(connection) ? connection : [connection];
  return values
    .flatMap((value) => value.split(','))
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);
}

export function safeProxyHeaders(headers, { request = false } = {}) {
  const blocked = new Set([
    ...HOP_BY_HOP_HEADERS,
    ...connectionHeaderNames(headers),
  ]);
  if (request) {
    blocked.add('host');
    for (const header of SPOOFABLE_FORWARDING_HEADERS) blocked.add(header);
  }

  return Object.fromEntries(
    Object.entries(headers).filter(
      ([name, value]) =>
        value !== undefined && !blocked.has(name.toLowerCase()),
    ),
  );
}

function isLoopbackHostname(hostname) {
  const normalized = hostname.replace(/^\[|\]$/gu, '').toLowerCase();
  if (normalized === 'localhost' || normalized === 'localhost.') return true;
  if (isIP(normalized) === 4) return normalized.split('.')[0] === '127';
  return normalized === '::1';
}

export function parseApiTarget(value) {
  if (!value) return null;

  let target;
  try {
    target = new URL(value);
  } catch (error) {
    throw new Error('Preview API target must be a valid URL', { cause: error });
  }

  if (!['http:', 'https:'].includes(target.protocol)) {
    throw new Error('Preview API target must use http or https');
  }
  if (target.username || target.password) {
    throw new Error('Preview API target must not contain credentials');
  }
  if (target.pathname !== '/' || target.search || target.hash) {
    throw new Error(
      'Preview API target must be an origin without a path, query, or fragment',
    );
  }
  if (!isLoopbackHostname(target.hostname)) {
    throw new Error(
      'Preview API target must be an explicit loopback/disposable origin',
    );
  }
  return target;
}

function proxyRequest(request, response, parsedTarget, apiTarget) {
  if (!apiTarget) {
    request.resume();
    sendText(
      request,
      response,
      503,
      'Backend route unavailable: no disposable preview API target was supplied',
    );
    return;
  }

  const transport =
    apiTarget.protocol === 'https:' ? createHttpsRequest : createHttpRequest;
  const upstream = transport(
    {
      protocol: apiTarget.protocol,
      hostname: apiTarget.hostname.replace(/^\[|\]$/gu, ''),
      port: apiTarget.port,
      method: request.method,
      path: `${parsedTarget.rawPathname}${parsedTarget.search}`,
      headers: safeProxyHeaders(request.headers, { request: true }),
    },
    (upstreamResponse) => {
      if (response.destroyed) {
        upstreamResponse.destroy();
        return;
      }

      response.writeHead(
        upstreamResponse.statusCode ?? 502,
        safeProxyHeaders(upstreamResponse.headers),
      );
      if (request.method === 'HEAD') {
        upstreamResponse.resume();
        response.end();
        return;
      }
      pipeline(upstreamResponse, response, (error) => {
        if (error && !response.destroyed) response.destroy(error);
      });
    },
  );

  upstream.setTimeout(PROXY_TIMEOUT_MS, () => {
    upstream.destroy(new Error('Preview API proxy timed out'));
  });
  upstream.on('error', () => {
    if (response.destroyed) return;
    if (response.headersSent) {
      response.destroy();
      return;
    }
    sendText(request, response, 502, 'Disposable preview API request failed');
  });
  request.once('aborted', () => upstream.destroy());
  pipeline(request, upstream, (error) => {
    if (error && !upstream.destroyed) upstream.destroy(error);
  });
}

export async function createStaticPreviewServer({
  apiTarget: requestedApiTarget,
  buildRoot = DEFAULT_BUILD_ROOT,
} = {}) {
  const canonicalBuildRoot = await realpath(buildRoot);
  const staticFiles = await indexStaticFiles(canonicalBuildRoot);
  const fallback = staticFiles.get('/200.html');
  if (!fallback) {
    throw new Error(
      `Static SPA fallback is missing from ${canonicalBuildRoot}`,
    );
  }
  const apiTarget =
    requestedApiTarget instanceof URL
      ? parseApiTarget(requestedApiTarget.href)
      : parseApiTarget(requestedApiTarget);

  return createHttpServer(async (request, response) => {
    try {
      const parsedTarget = parseRequestTarget(request.url ?? '');
      if (classifyRoute(parsedTarget.rawPathname) === 'backend') {
        proxyRequest(request, response, parsedTarget, apiTarget);
        return;
      }

      if (request.method !== 'GET' && request.method !== 'HEAD') {
        request.resume();
        sendText(request, response, 405, 'Method not allowed', {
          Allow: 'GET, HEAD',
        });
        return;
      }

      const file =
        staticFiles.get(normalizeStaticLookupPathname(parsedTarget.pathname)) ??
        null;
      serveFile(request, response, file ?? fallback, file === null);
    } catch (error) {
      request.resume();
      if (response.destroyed || response.headersSent) {
        if (!response.destroyed) response.destroy(error);
        return;
      }
      if (error instanceof UnsafeRequestTargetError) {
        sendText(request, response, 400, 'Bad request path');
        return;
      }
      sendText(request, response, 500, 'Static preview server error');
    }
  });
}

function readOptionValue(argumentsList, index, option) {
  const value = argumentsList[index + 1];
  if (!value || value.startsWith('-')) {
    throw new Error(`${option} requires a value`);
  }
  return value;
}

export function parseCliArguments(argumentsList, environment = process.env) {
  const options = {
    apiTarget: environment.ED_FINDER_PREVIEW_API_TARGET?.trim() || undefined,
    host: DEFAULT_HOST,
    port: DEFAULT_PORT,
  };

  for (let index = 0; index < argumentsList.length; index += 1) {
    const argument = argumentsList[index];
    if (argument === '--') continue;
    if (argument === '--strictPort') {
      // Node's listen call never searches for another port, so it already has
      // Vite's strict-port behaviour. Keep accepting the existing CI flag.
      continue;
    }

    const [name, inlineValue] = argument.split('=', 2);
    if (name === '--host' || name === '--port' || name === '--api-target') {
      const value = inlineValue ?? readOptionValue(argumentsList, index, name);
      if (inlineValue === undefined) index += 1;
      if (name === '--host') options.host = value;
      if (name === '--port') options.port = Number(value);
      if (name === '--api-target') options.apiTarget = value;
      continue;
    }
    throw new Error(`Unsupported static preview option: ${argument}`);
  }

  if (!options.host) throw new Error('Preview host must not be empty');
  if (
    !Number.isInteger(options.port) ||
    options.port < 1 ||
    options.port > 65_535
  ) {
    throw new Error('Preview port must be an integer from 1 through 65535');
  }
  parseApiTarget(options.apiTarget);
  return options;
}

async function listen(server, host, port) {
  await new Promise((resolvePromise, rejectPromise) => {
    const onError = (error) => {
      server.off('listening', onListening);
      rejectPromise(error);
    };
    const onListening = () => {
      server.off('error', onError);
      resolvePromise();
    };
    server.once('error', onError);
    server.once('listening', onListening);
    server.listen(port, host);
  });
}

function installTerminationHandlers(server) {
  let closing = false;
  let forceCloseTimer;

  const shutdown = (signal) => {
    if (closing) {
      server.closeAllConnections();
      return;
    }
    closing = true;
    process.stderr.write(`[static-preview] ${signal}; closing\n`);
    server.close((error) => {
      if (forceCloseTimer) clearTimeout(forceCloseTimer);
      if (error) {
        process.stderr.write(
          `[static-preview] shutdown failed: ${error.message}\n`,
        );
        process.exitCode = 1;
      }
    });
    server.closeIdleConnections();
    forceCloseTimer = setTimeout(() => server.closeAllConnections(), 5_000);
    forceCloseTimer.unref();
  };

  process.once('SIGINT', shutdown);
  process.once('SIGTERM', shutdown);
}

async function main() {
  const options = parseCliArguments(process.argv.slice(2));
  const server = await createStaticPreviewServer({
    apiTarget: options.apiTarget,
  });
  await listen(server, options.host, options.port);
  installTerminationHandlers(server);
  process.stdout.write(
    `[static-preview] listening on http://${options.host}:${options.port} (API proxy ${
      options.apiTarget ? 'enabled' : 'disabled/fail-closed'
    })\n`,
  );
}

const invokedPath = process.argv[1]
  ? pathToFileURL(resolve(process.argv[1])).href
  : null;
if (invokedPath === import.meta.url) {
  main().catch((error) => {
    process.stderr.write(`[static-preview] ${error.message}\n`);
    process.exitCode = 1;
  });
}
