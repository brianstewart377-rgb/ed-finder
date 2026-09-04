"""Fail-closed repository contracts for the Svelte platform tranche (#579)."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"
SOURCE = WEB / "src"


def _application_sources():
    for suffix in ("*.ts", "*.svelte"):
        for path in SOURCE.rglob(suffix):
            relative = path.relative_to(SOURCE).as_posix()
            if "/generated/" in f"/{relative}" or relative.endswith(".test.ts"):
                continue
            yield path, path.read_text(encoding="utf-8")


def test_generated_hey_api_is_isolated_behind_api_adapters():
    offenders = []
    for path, source in _application_sources():
        relative = path.relative_to(SOURCE).as_posix()
        if "/api/" not in f"/{relative}" and re.search(
            r"(?:from|import\()\s*['\"][^'\"]*api/generated", source
        ):
            offenders.append(relative)
    assert offenders == []


def test_application_id64_never_uses_number_coercion_or_number_types():
    coercion = re.compile(
        r"(?:Number|parseInt)\s*\([^\n)]*(?:id64|systemId|system_id)|"
        r"\+\s*(?:[A-Za-z_$][\w$]*\.)*(?:id64|systemId|system_id)\b",
        re.IGNORECASE,
    )
    number_type = re.compile(
        r"(?:id64|systemId64|system_id64)\??\s*:\s*number\b", re.IGNORECASE
    )
    offenders = []
    for path, source in _application_sources():
        if coercion.search(source) or number_type.search(source):
            offenders.append(path.relative_to(SOURCE).as_posix())
    assert offenders == []


def test_persisted_key_inventory_is_explicit_and_complete():
    persistence = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (SOURCE / "lib" / "persistence").glob("*.ts")
    )
    local_keys = {
        "ed_pinned",
        "ed_compare_v2",
        "ed_sync_key",
        "ed_selected_route",
        "ed_my_work_v1",
        "ed_colony_projects_v1",
        "ed_expansion_plans_v1",
        "ed_fc_v2",
        "ed_profile_sync_key",
        "ed_profile_sync_last",
        "ed-finder:selected-system-context",
        "ed_density_v1",
    }
    session_keys = {"ed_admin_token", "ed_operator_selected_source_run"}
    assert all(
        f"'{key}'" in persistence or f'"{key}"' in persistence
        for key in local_keys | session_keys
    )
    assert "localStorage" in persistence
    assert "sessionStorage" in persistence


def test_static_application_has_no_pwa_or_playwright_runtime():
    package = (WEB / "package.json").read_text(encoding="utf-8").lower()
    paths = {
        path.name.lower()
        for root in (SOURCE, WEB / "static")
        if root.exists()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert "playwright" not in package
    assert "serviceworker" not in package
    assert not ({"manifest.webmanifest", "service-worker.js", "sw.js"} & paths)


def test_backend_route_ownership_remains_exact_and_frontend_is_fallback():
    vite = (WEB / "vite.config.ts").read_text(encoding="utf-8")
    svelte = (WEB / "svelte.config.js").read_text(encoding="utf-8")
    assert "^/api(?:$|[/?])" in vite
    assert r"^/openapi\\.json(?:\\?.*)?$" in vite
    assert r"^/s/\\d+(?:\\?.*)?$" in vite
    assert "fallback: '200.html'" in svelte


def test_react_tree_is_retained_as_source_evidence_only():
    assert (ROOT / "frontend" / "src" / "App.tsx").is_file()
    assert (WEB / "src" / "routes").is_dir()


def test_root_layout_owns_the_configured_query_and_persistence_singletons():
    layout = (SOURCE / "routes" / "+layout.svelte").read_text(encoding="utf-8")
    query = (SOURCE / "lib" / "api" / "query.ts").read_text(encoding="utf-8")
    shell = (SOURCE / "lib" / "components" / "AppShell.svelte").read_text(
        encoding="utf-8"
    )
    assert "new QueryClient" not in layout
    assert "import { queryClient } from '$lib/api/query'" in layout
    for accepted_default in (
        "staleTime: 30_000",
        "gcTime: 300_000",
        "retry: 1",
        "refetchOnWindowFocus: false",
        "mutations: { retry: 0 }",
    ):
        assert accepted_default in query
    assert "providePersistenceContext()" in layout
    assert "hydrateApplicationStores()" in shell
