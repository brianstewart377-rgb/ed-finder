"""Repository contracts for the first V3 Svelte web foundation.

These checks keep the new application lane distinct from the retained React
reference application and prevent migration tooling choices from drifting.
"""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def _package_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v3_web_uses_the_locked_svelte_node_and_pnpm_foundation():
    package = _package_json(WEB / "package.json")
    dependencies = package.get("dependencies", {})
    dev_dependencies = package.get("devDependencies", {})
    packages = dependencies | dev_dependencies

    assert package["packageManager"] == "pnpm@11.25.0"
    assert package["engines"]["node"] == ">=24 <25"
    assert packages["svelte"].lstrip("^~").startswith("5.")
    assert packages["@sveltejs/kit"].lstrip("^~").startswith("2.")
    assert (WEB / "pnpm-lock.yaml").is_file()


def test_v3_web_lib_modules_are_not_hidden_by_the_root_python_ignore_rule():
    root_gitignore = _read(".gitignore").splitlines()

    assert "lib/" in root_gitignore
    assert "!apps/web/src/lib/" in root_gitignore
    assert "!apps/web/src/lib/**" in root_gitignore


def test_v3_web_uses_locked_lint_and_format_tooling():
    package = _package_json(WEB / "package.json")
    dev_dependencies = package["devDependencies"]
    eslint_config = _read("apps", "web", "eslint.config.js")

    assert dev_dependencies["eslint"].lstrip("^~").startswith("10.")
    assert "eslint-plugin-svelte" in dev_dependencies
    assert "typescript-eslint" in dev_dependencies
    assert dev_dependencies["prettier"].lstrip("^~").startswith("3.")
    assert "prettier-plugin-svelte" in dev_dependencies
    assert "eslint" in package["scripts"]["lint"]
    assert "prettier --check" in package["scripts"]["format:check"]
    assert "svelte-check" in package["scripts"]["check"]
    assert "eslint-plugin-svelte" in eslint_config


def test_bootstrap_client_delegates_to_generated_hey_api_sdk():
    client = _read("apps", "web", "src", "lib", "api", "client.ts")

    assert "from './generated/sdk.gen'" in client
    assert "generatedGetHealth" in client
    assert "generatedGetAuthSession" in client
    assert "fetch(" not in client
    assert "getJson" not in client


def test_svelte_ci_checks_generated_client_quality_and_build():
    workflow = _read(".github", "workflows", "ci.yml")

    for command in (
        "pnpm generate:api",
        "git diff --exit-code -- src/lib/api/generated",
        "pnpm check",
        "pnpm lint",
        "pnpm format:check",
        "pnpm test",
        "pnpm build",
    ):
        assert command in workflow


def test_legacy_react_frontend_remains_migration_reference():
    legacy_package = _package_json(ROOT / "frontend" / "package.json")
    readme = _read("README.md")

    assert (ROOT / "frontend").is_dir()
    assert "react" in legacy_package["dependencies"]
    assert legacy_package["packageManager"] == "yarn@1.22.22"
    assert "migration/reference" in readme


def test_cypress_is_the_v3_web_browser_authority():
    stack_decision = _read("docs", "development", "v3-application-stack-decision.md")
    cypress_config = WEB / "cypress.config.ts"

    assert "**Cypress is the protected browser/E2E authority**" in stack_decision
    assert cypress_config.is_file()
    assert any((WEB / "cypress").glob("e2e/*.cy.ts"))


def test_v3_web_does_not_import_retired_or_deferred_runtime_dependencies():
    package = _package_json(WEB / "package.json")
    package_names = set(package.get("dependencies", {})) | set(
        package.get("devDependencies", {})
    )
    forbidden_names = {"babylonjs", "playwright", "react", "react-dom", "three"}
    forbidden_prefixes = ("@babylonjs/", "@playwright/", "@react-three/")

    assert package_names.isdisjoint(forbidden_names)
    assert not [name for name in package_names if name.startswith(forbidden_prefixes)]


def test_v3_web_is_static_spa_and_backend_route_ownership_is_explicit():
    svelte_config = _read("apps", "web", "svelte.config.js")
    readme = _read("README.md")

    assert "@sveltejs/adapter-static" in svelte_config
    assert "fallback: '200.html'" in svelte_config or 'fallback: "200.html"' in svelte_config
    assert "/api/*" in readme
    assert "exact `/openapi.json`" in readme
    assert "numeric `/s/{id64}`" in readme
    assert "SvelteKit" in readme
