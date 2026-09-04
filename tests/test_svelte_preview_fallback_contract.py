from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
VITE_CONFIG = ROOT / 'apps' / 'web' / 'vite.config.ts'


@pytest.mark.unit
def test_svelte_preview_serves_only_known_dynamic_application_namespaces():
    source = VITE_CONFIG.read_text(encoding='utf-8')

    assert "name: 'ed-finder-static-spa-preview-fallback'" in source
    assert 'configurePreviewServer(server)' in source
    assert "method !== 'GET' && method !== 'HEAD'" in source
    assert "request.headers.accept" not in source
    assert r'/^\/system\/\d+\/?$/' in source
    assert r'/^\/colony-planner(?:\/.*)?\/?$/' in source
    assert "new URL('./build/200.html', import.meta.url)" in source
    assert "readFile(staticSpaFallbackFile, 'utf8')" in source
    assert "response.statusCode = 200" in source
    assert "response.setHeader('Content-Type', 'text/html; charset=utf-8')" in source
    assert "response.end(method === 'HEAD' ? undefined : html)" in source
    assert 'request.url = `/200.html${url.search}`;' not in source


@pytest.mark.unit
def test_svelte_preview_keeps_backend_and_unknown_frontend_routes_out_of_fallback():
    source = VITE_CONFIG.read_text(encoding='utf-8')
    fallback_block = source[
        source.index('const staticSpaRoutes'):
        source.index('export function isStaticSpaRoute')
    ]

    assert 'api' not in fallback_block
    assert 'openapi' not in fallback_block
    assert '/s/' not in fallback_block
    assert 'apiary' not in fallback_block
    assert "'^/api(?:$|[/?])'" in source
    assert "'^/openapi\\\\.json(?:\\\\?.*)?$'" in source
    assert "'^/s/\\\\d+(?:\\\\?.*)?$'" in source
