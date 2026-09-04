import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import {
  createServer as createHttpServer,
  request as httpRequest,
} from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after, before, describe, test } from 'node:test';

import {
  UnsafeRequestTargetError,
  classifyRoute,
  createStaticPreviewServer,
  parseApiTarget,
  parseCliArguments,
  parseRequestTarget,
  safeProxyHeaders,
} from './static-preview.mjs';

const FALLBACK_HTML = '<!doctype html><title>ED-Finder fallback</title>';

async function listen(server) {
  await new Promise((resolvePromise, rejectPromise) => {
    server.once('error', rejectPromise);
    server.listen(0, '127.0.0.1', resolvePromise);
  });
  const address = server.address();
  assert(address && typeof address === 'object');
  return `http://127.0.0.1:${address.port}`;
}

async function close(server) {
  await new Promise((resolvePromise, rejectPromise) => {
    server.close((error) => (error ? rejectPromise(error) : resolvePromise()));
    server.closeIdleConnections();
  });
}

function rawRequest(origin, path, options = {}) {
  return new Promise((resolvePromise, rejectPromise) => {
    const url = new URL(origin);
    const request = httpRequest(
      {
        hostname: url.hostname,
        port: url.port,
        method: options.method ?? 'GET',
        path,
        headers: options.headers,
      },
      (response) => {
        const chunks = [];
        response.on('data', (chunk) => chunks.push(chunk));
        response.on('end', () => {
          resolvePromise({
            body: Buffer.concat(chunks).toString('utf8'),
            headers: response.headers,
            status: response.statusCode,
          });
        });
      },
    );
    request.on('error', rejectPromise);
    if (options.body) request.write(options.body);
    request.end();
  });
}

describe('static preview route ownership', () => {
  test('classifies only exact backend-owned path shapes', () => {
    const backendTargets = [
      '/api',
      '/api?fresh=1',
      '/api/',
      '/api/health?fresh=1',
      '/openapi.json',
      '/openapi.json?format=json',
      '/s/0?utm=x',
      '/s/18446744073709551615',
    ];
    const frontendTargets = [
      '/',
      '/apiary',
      '/openapi.jsonx',
      '/openapi.json/extra',
      '/s/not-a-number',
      '/s/1/extra',
      '/s/1x',
      '/system/18446744073709551615',
      '/colony-planner/system/1/project/a',
    ];

    for (const target of backendTargets) {
      const parsed = parseRequestTarget(target);
      assert.equal(classifyRoute(parsed.rawPathname), 'backend', target);
    }
    for (const target of frontendTargets) {
      const parsed = parseRequestTarget(target);
      assert.equal(classifyRoute(parsed.rawPathname), 'frontend', target);
    }
    assert.equal(classifyRoute('/api%2fhealth'), 'frontend');
  });

  test('keeps the query out of the static lookup pathname', () => {
    const parsed = parseRequestTarget(
      '/assets/app.js?file=../../package.json&route=/api/health',
    );

    assert.equal(parsed.pathname, '/assets/app.js');
    assert.equal(parsed.search, '?file=../../package.json&route=/api/health');
  });

  test('rejects malformed, null, backslash, and traversal paths', () => {
    const unsafeTargets = [
      '/bad%',
      '/bad%E0%A4%A',
      '/bad%00path',
      '/bad\\path',
      '/bad%5cpath',
      '/../package.json',
      '/safe/./asset.js',
      '/%2e%2e/package.json',
      '/safe%2f..%2f..%2fpackage.json',
      '/safe?bad=%',
    ];

    for (const target of unsafeTargets) {
      assert.throws(
        () => parseRequestTarget(target),
        UnsafeRequestTargetError,
        target,
      );
    }
  });
});

describe('static preview configuration', () => {
  test('accepts the existing preview CLI shape and an explicit target', () => {
    assert.deepEqual(
      parseCliArguments(
        ['--host', '127.0.0.1', '--port', '4174', '--strictPort'],
        { ED_FINDER_PREVIEW_API_TARGET: 'http://127.0.0.1:8002' },
      ),
      {
        apiTarget: 'http://127.0.0.1:8002',
        host: '127.0.0.1',
        port: 4174,
      },
    );
  });

  test('allows no target but rejects credentials and non-loopback hosts', () => {
    const credentialTarget = new URL('http://127.0.0.1:8002');
    credentialTarget.username = 'preview-user';
    credentialTarget.password = 'disposable-placeholder';

    assert.equal(parseApiTarget(undefined), null);
    assert.equal(parseApiTarget('http://127.0.0.1:8002').port, '8002');
    assert.throws(() => parseApiTarget(credentialTarget.href));
    assert.throws(() => parseApiTarget('https://example.com'));
    assert.throws(() => parseApiTarget('http://127.0.0.1:8002/api'));
  });

  test('removes hop-by-hop and spoofable forwarding headers', () => {
    assert.deepEqual(
      safeProxyHeaders(
        {
          authorization: 'Bearer disposable-test-token',
          connection: 'keep-alive, x-remove-me',
          host: 'preview.invalid',
          'x-forwarded-for': '203.0.113.10',
          'x-keep-me': 'yes',
          'x-remove-me': 'no',
        },
        { request: true },
      ),
      {
        authorization: 'Bearer disposable-test-token',
        'x-keep-me': 'yes',
      },
    );
  });
});

describe('static preview HTTP contract', () => {
  let buildRoot;
  let previewOrigin;
  let previewServer;

  before(async () => {
    buildRoot = await mkdtemp(join(tmpdir(), 'ed-finder-static-preview-'));
    await mkdir(join(buildRoot, 'assets'));
    await mkdir(join(buildRoot, 'guide'));
    await writeFile(join(buildRoot, '200.html'), FALLBACK_HTML);
    await writeFile(
      join(buildRoot, 'index.html'),
      '<!doctype html><title>index</title>',
    );
    await writeFile(
      join(buildRoot, 'assets', 'app.css'),
      'body { color: red; }',
    );
    await writeFile(
      join(buildRoot, 'guide', 'index.html'),
      '<!doctype html><title>guide</title>',
    );
    previewServer = await createStaticPreviewServer({ buildRoot });
    previewOrigin = await listen(previewServer);
  });

  after(async () => {
    if (previewServer) await close(previewServer);
    if (buildRoot) await rm(buildRoot, { recursive: true, force: true });
  });

  test('serves exact static files with their content type and ignores queries', async () => {
    const response = await fetch(
      `${previewOrigin}/assets/app.css?file=../../package.json`,
    );
    assert.equal(response.status, 200);
    assert.match(response.headers.get('content-type'), /^text\/css/u);
    assert.equal(await response.text(), 'body { color: red; }');

    const repeatedSlashResponse = await fetch(
      `${previewOrigin}/assets//app.css`,
    );
    assert.equal(repeatedSlashResponse.status, 200);
    assert.match(
      repeatedSlashResponse.headers.get('content-type'),
      /^text\/css/u,
    );
    assert.equal(await repeatedSlashResponse.text(), 'body { color: red; }');

    for (const path of ['/guide', '/guide/', '/guide/index.html']) {
      const indexResponse = await fetch(`${previewOrigin}${path}`);
      assert.equal(indexResponse.status, 200, path);
      assert.equal(
        await indexResponse.text(),
        '<!doctype html><title>guide</title>',
        path,
      );
    }
  });

  test('serves unknown frontend routes from 200.html for GET and HEAD', async () => {
    for (const path of [
      '/system/18446744073709551615',
      '/colony-planner/system/18446744073709551615/project/a/mode/preview',
      '/apiary',
      '/openapi.jsonx',
      '/s/not-a-number',
      '/unknown-frontend-route',
    ]) {
      const getResponse = await fetch(`${previewOrigin}${path}`);
      assert.equal(getResponse.status, 200, path);
      assert.match(
        getResponse.headers.get('content-type'),
        /^text\/html/u,
        path,
      );
      assert.equal(await getResponse.text(), FALLBACK_HTML, path);
    }

    const headResponse = await fetch(`${previewOrigin}/apiary`, {
      method: 'HEAD',
    });
    assert.equal(headResponse.status, 200);
    assert.match(headResponse.headers.get('content-type'), /^text\/html/u);
    assert.equal(
      headResponse.headers.get('content-length'),
      String(Buffer.byteLength(FALLBACK_HTML)),
    );
    assert.equal(await headResponse.text(), '');
  });

  test('fails closed for every backend-owned route without an explicit target', async () => {
    for (const path of [
      '/api',
      '/api/health?fresh=1',
      '/openapi.json?format=json',
      '/s/18446744073709551615',
    ]) {
      const response = await fetch(`${previewOrigin}${path}`);
      assert.equal(response.status, 503, path);
      assert.match(response.headers.get('content-type'), /^text\/plain/u, path);
      assert.doesNotMatch(await response.text(), /ED-Finder fallback/u, path);
    }
  });

  test('does not expose files added after the startup index is sealed', async () => {
    await writeFile(join(buildRoot, 'late.txt'), 'not indexed');

    const response = await fetch(`${previewOrigin}/late.txt`);
    assert.equal(response.status, 200);
    assert.match(response.headers.get('content-type'), /^text\/html/u);
    assert.equal(await response.text(), FALLBACK_HTML);
  });

  test('rejects traversal-like request bytes without exposing repository files', async () => {
    for (const path of [
      '/bad%E0%A4%A',
      '/bad%00path',
      '/%5c..%5cpackage.json',
      '/safe%2f..%2f..%2fpackage.json',
    ]) {
      const response = await rawRequest(previewOrigin, path);
      assert.equal(response.status, 400, path);
      assert.equal(response.body, 'Bad request path\n', path);
      assert.doesNotMatch(
        response.body,
        /@ed-finder\/web|ED-Finder Agent Contract/u,
      );
    }
  });
});

describe('static preview streaming proxy', () => {
  let apiOrigin;
  let apiServer;
  let buildRoot;
  let previewOrigin;
  let previewServer;

  before(async () => {
    buildRoot = await mkdtemp(join(tmpdir(), 'ed-finder-static-proxy-'));
    await writeFile(join(buildRoot, '200.html'), FALLBACK_HTML);

    apiServer = createHttpServer((request, response) => {
      response.writeHead(201, {
        'Content-Type': 'application/octet-stream',
        'X-Observed-Authorization': request.headers.authorization ?? 'missing',
        'X-Observed-Forwarded-For':
          request.headers['x-forwarded-for'] ?? 'missing',
        'X-Observed-Host': request.headers.host ?? 'missing',
        'X-Observed-Path': request.url,
      });
      request.pipe(response);
    });
    apiOrigin = await listen(apiServer);
    previewServer = await createStaticPreviewServer({
      apiTarget: apiOrigin,
      buildRoot,
    });
    previewOrigin = await listen(previewServer);
  });

  after(async () => {
    if (previewServer) await close(previewServer);
    if (apiServer) await close(apiServer);
    if (buildRoot) await rm(buildRoot, { recursive: true, force: true });
  });

  test('streams request and response bodies while preserving the raw query', async () => {
    const payload = 'streamed request body';
    const response = await fetch(`${previewOrigin}/api/echo?format=raw`, {
      method: 'POST',
      body: payload,
      headers: {
        Authorization: 'Bearer disposable-test-token',
        'X-Forwarded-For': '203.0.113.10',
      },
    });

    assert.equal(response.status, 201);
    assert.equal(
      response.headers.get('x-observed-path'),
      '/api/echo?format=raw',
    );
    assert.equal(
      response.headers.get('x-observed-authorization'),
      'Bearer disposable-test-token',
    );
    assert.equal(response.headers.get('x-observed-forwarded-for'), 'missing');
    assert.equal(
      response.headers.get('x-observed-host'),
      new URL(apiOrigin).host,
    );
    assert.equal(await response.text(), payload);
  });

  test('proxies every exact backend route shape', async () => {
    for (const path of [
      '/api',
      '/api/health?fresh=1',
      '/openapi.json?format=json',
      '/s/18446744073709551615',
    ]) {
      const response = await fetch(`${previewOrigin}${path}`);
      assert.equal(response.status, 201, path);
      assert.equal(response.headers.get('x-observed-path'), path, path);
    }
  });
});
