import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"
PREVIEW_SERVER = WEB / "scripts" / "static-preview.mjs"


@pytest.mark.unit
def test_svelte_preview_uses_the_built_static_server_contract():
    package = json.loads((WEB / "package.json").read_text(encoding="utf-8"))
    source = PREVIEW_SERVER.read_text(encoding="utf-8")
    vite = (WEB / "vite.config.ts").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "cypress-parity.yml").read_text(
        encoding="utf-8"
    )

    assert package["scripts"]["preview"] == "node scripts/static-preview.mjs"
    assert "node --test scripts/static-preview.test.mjs" in package["scripts"]["test"]
    assert "name: 'ed-finder-static-spa-preview-fallback'" not in vite
    assert "preview: { proxy: backendProxy }" not in vite
    assert "ED_FINDER_PREVIEW_API_TARGET: http://127.0.0.1:8002" in workflow
    assert "pnpm preview --host 127.0.0.1 --port 4174 --strictPort" in workflow

    assert "const staticFiles = await indexStaticFiles(canonicalBuildRoot)" in source
    assert "const fallback = staticFiles.get('/200.html')" in source
    assert "request.method !== 'GET' && request.method !== 'HEAD'" in source
    assert "serveFile(request, response, file ?? fallback, file === null)" in source
    serve_file = source[
        source.index("function serveFile") : source.index(
            "function connectionHeaderNames"
        )
    ]
    assert "response.writeHead(" in serve_file
    assert "200," in serve_file
    assert "response.end(request.method === 'HEAD' ? undefined : body)" in source
    assert "request.headers.accept" not in source


@pytest.mark.unit
def test_svelte_preview_keeps_backend_ownership_exact_and_fails_closed():
    source = PREVIEW_SERVER.read_text(encoding="utf-8")

    assert r"/^\/api(?:\/|$)/u" in source
    assert r"/^\/openapi\.json$/u" in source
    assert r"/^\/s\/[0-9]+$/u" in source
    assert "classifyRoute(parsedTarget.rawPathname) === 'backend'" in source
    assert "? 'backend'" in source
    assert ": 'frontend'" in source
    assert "parsedTarget.rawPathname}${parsedTarget.search}" in source
    assert "no disposable preview API target was supplied" in source
    assert "503" in source

    assert "target.username || target.password" in source
    assert "isLoopbackHostname(target.hostname)" in source
    assert "pipeline(request, upstream" in source
    assert "process.once('SIGINT', shutdown)" in source
    assert "process.once('SIGTERM', shutdown)" in source


@pytest.mark.unit
def test_svelte_preview_indexes_static_paths_before_handling_requests():
    source = PREVIEW_SERVER.read_text(encoding="utf-8")

    assert "requestTarget.indexOf('?')" in source
    assert "decodeUrlComponent(rawPathname, 'request path')" in source
    assert "pathname.includes('\\\\')" in source
    assert "segment === '.' || segment === '..'" in source
    assert "await readdir(directory, { withFileTypes: true })" in source
    assert "const canonicalPath = await realpath(entryPath)" in source
    assert "staticFiles.get(" in source
    assert "normalizeStaticLookupPathname(parsedTarget.pathname)" in source
    assert "resolveStaticPath(buildRoot, pathname)" not in source

    request_handler = source[
        source.index(
            "return createHttpServer(async (request, response)"
        ) : source.index("function readOptionValue")
    ]
    assert "stat(" not in request_handler
    assert "realpath(" not in request_handler
    assert "'Content-Type'" in source
    assert "'Content-Length'" in source
