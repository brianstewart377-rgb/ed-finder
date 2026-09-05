"""Repository contracts for the first V3 Svelte web foundation.

These checks keep the new application lane distinct from the retained React
reference application and prevent migration tooling choices from drifting.
"""

import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def _package_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _vite_backend_proxy_patterns() -> list[re.Pattern[str]]:
    config = _read("apps", "web", "vite.config.ts")
    proxy_block = config.split("const backendProxy = {", 1)[1].split("};", 1)[0]
    encoded_patterns = re.findall(
        r"^\s*('(?:[^'\\]|\\.)*')\s*:", proxy_block, re.MULTILINE
    )
    patterns = [json.loads(f'"{value[1:-1]}"') for value in encoded_patterns]

    assert "server: { proxy: backendProxy }" in config
    assert "preview: { proxy: backendProxy }" in config
    return [re.compile(pattern) for pattern in patterns]


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


def test_v3_web_pnpm_workspace_enforces_supply_chain_policy():
    workspace = yaml.safe_load((WEB / "pnpm-workspace.yaml").read_text(encoding="utf-8"))
    exclusions = workspace["minimumReleaseAgeExclude"]

    assert workspace["blockExoticSubdeps"] is True
    assert workspace["minimumReleaseAge"] == 10080
    assert workspace["trustPolicy"] == "no-downgrade"
    assert exclusions
    assert all(isinstance(exclusion, str) for exclusion in exclusions)
    assert not any("*" in exclusion for exclusion in exclusions)
    assert all(
        re.fullmatch(
            r"(?:@[^/@\s]+/)?[^@/\s]+@\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?",
            exclusion,
        )
        for exclusion in exclusions
    )


def test_shared_source_packages_use_file_dependencies_without_expanding_the_pnpm_workspace():
    api_client = _package_json(ROOT / "packages" / "api-client" / "package.json")
    planner_core = _package_json(ROOT / "packages" / "planner-core" / "package.json")
    react = _package_json(ROOT / "frontend" / "package.json")
    web = _package_json(WEB / "package.json")
    workspace = yaml.safe_load((WEB / "pnpm-workspace.yaml").read_text(encoding="utf-8"))

    assert api_client["private"] is True
    assert api_client["type"] == "module"
    assert api_client["exports"]["./*"]["import"] == "./src/*.ts"
    assert planner_core["private"] is True
    assert planner_core["type"] == "module"
    assert planner_core["exports"]["./*"]["import"] == "./src/*.ts"
    assert planner_core["exports"]["./comparison"]["import"] == "./src/comparison/index.ts"
    assert planner_core["exports"]["./journal"]["import"] == "./src/journal/index.ts"
    assert planner_core["dependencies"] == {"json-with-bigint": "3.5.11"}
    assert planner_core["peerDependencies"] == {"@ed-finder/api-client": "0.1.0"}
    assert react["dependencies"]["@ed-finder/api-client"] == "file:../packages/api-client"
    assert react["dependencies"]["@ed-finder/planner-core"] == "file:../packages/planner-core"
    assert workspace["packages"] == ["."]
    assert "@ed-finder/api-client" not in web.get("dependencies", {})
    assert "@ed-finder/planner-core" not in web.get("dependencies", {})
    assert web["devDependencies"]["json-with-bigint"] == "3.5.11"


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
    assert package["scripts"]["format"] == "prettier --write ."
    assert package["scripts"]["format:check"] == "prettier --check ."
    assert "svelte-check" in package["scripts"]["check"]
    assert "eslint-plugin-svelte" in eslint_config


def test_bootstrap_client_delegates_to_generated_hey_api_sdk():
    client = _read("apps", "web", "src", "lib", "api", "client.ts")

    assert "from './generated/sdk.gen'" in client
    assert "generatedGetHealth" in client
    assert "generatedGetAuthSession" in client
    assert "fetch(" not in client
    assert "getJson" not in client


def test_svelte_generation_snapshots_explicit_authoritative_openapi_input():
    package = _package_json(WEB / "package.json")
    config = _read("apps", "web", "openapi-ts.config.ts")
    capture = _read("apps", "web", "scripts", "capture-openapi.mjs")
    generated_client = _read(
        "apps", "web", "src", "lib", "api", "generated", "client.gen.ts"
    )
    generated_types = _read(
        "apps", "web", "src", "lib", "api", "generated", "types.gen.ts"
    )

    assert "node scripts/capture-openapi.mjs" in package["scripts"]["generate:api"]
    assert "process.env.OPENAPI_INPUT" in config
    assert "if (!requestedInput)" in config
    assert "input: './.svelte-kit/openapi.json'" in config
    assert "baseUrl: false" in config
    assert "name: '@hey-api/client-fetch'" in config
    assert "process.env.OPENAPI_INPUT" in capture
    assert "await fetch(input" in capture
    assert "JSON.parse(rawSchema)" in capture
    assert "'.svelte-kit', 'openapi.json'" in capture
    assert "bootstrap.openapi.json" not in config
    assert "127.0.0.1" not in generated_client
    assert "127.0.0.1" not in generated_types
    assert not (WEB / "openapi" / "bootstrap.openapi.json").exists()


def test_svelte_ci_checks_generated_client_quality_and_build():
    workflow = _read(".github", "workflows", "ci.yml")
    web_job = workflow.split("  web:\n", 1)[1].split("  nginx:\n", 1)[0]

    for command in (
        "pnpm run shared:check",
        "pnpm run shared:lint",
        "pnpm run shared:test",
        "pnpm run shared:build",
        "pnpm check",
        "pnpm lint",
        "pnpm format:check",
        "pnpm test",
        "pnpm build",
    ):
        assert command in web_job

    assert "pnpm generate:api" not in web_job


def test_openapi_drift_lane_generates_both_clients_from_the_running_api():
    workflow = _read(".github", "workflows", "ci.yml")
    drift_job = workflow.split("  openapi-types:\n", 1)[1]
    script = _read("scripts", "checks", "openapi-drift.sh")
    react_generator = _read("frontend", "scripts", "types-gen.mjs")

    assert 'node-version: "24"' in drift_job
    assert "corepack prepare pnpm@11.25.0 --activate" in drift_job
    assert "pnpm install --frozen-lockfile" in drift_job
    assert "OPENAPI_INPUT: http://127.0.0.1:8000/openapi.json" in drift_job
    assert "git diff --exit-code -- apps/web/src/lib/api/generated" in drift_job
    assert "git diff --exit-code -- packages/api-client/src/generated/api.gen.ts" in drift_job
    assert 'VITE_OPENAPI_URL="$OPENAPI_URL"' in script
    assert 'OPENAPI_INPUT="$OPENAPI_URL"' in script
    assert "apps/web/src/lib/api/generated" in script
    assert "packages/api-client/src/generated/api.gen.ts" in script
    assert "packages/api-client/src/generated/api.gen.ts" in react_generator


def test_legacy_generated_api_compatibility_shim_stays_public():
    compatibility_entry = "src/types/api.gen.ts"
    frontend = ROOT / "frontend"
    knip = _package_json(frontend / "knip.json")
    shim = _read("frontend", *compatibility_entry.split("/"))
    generator = _read("frontend", "scripts", "types-gen.mjs")
    workflow = _read(".github", "workflows", "ci.yml")
    v2_job = workflow.split("  v2:\n", 1)[1].split("  web:\n", 1)[0]
    source_presence = v2_job.split(
        "- name: Verify required source files are present\n", 1
    )[1].split("- name: Install dependencies\n", 1)[0]

    assert compatibility_entry in knip["entry"]
    assert shim == "export * from '../../../packages/api-client/src/generated/api.gen';\n"
    assert (
        "const output = path.resolve(repoRoot, "
        "'packages/api-client/src/generated/api.gen.ts');"
    ) in generator
    assert compatibility_entry in source_presence


def test_legacy_react_frontend_remains_temporary_source_evidence():
    legacy_package = _package_json(ROOT / "frontend" / "package.json")
    readme = _read("README.md")

    assert (ROOT / "frontend").is_dir()
    assert "react" in legacy_package["dependencies"]
    assert legacy_package["packageManager"] == "yarn@1.22.22"
    assert "temporary source evidence" in readme
    assert "apps/web/" in readme


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


def test_vite_proxy_claims_only_backend_owned_route_boundaries():
    patterns = _vite_backend_proxy_patterns()

    backend_urls = (
        "/api",
        "/api?fresh=1",
        "/api/health",
        "/api/health?fresh=1",
        "/openapi.json",
        "/openapi.json?format=json",
        "/s/0",
        "/s/0?utm=x",
        "/s/18446744073709551615",
    )
    frontend_urls = (
        "/apiary",
        "/openapi.json/extra",
        "/openapi.jsonx",
        "/s/not-a-number",
        "/s/0/extra",
        "/s/0x",
    )

    assert all(any(pattern.match(url) for pattern in patterns) for url in backend_urls)
    assert all(not any(pattern.match(url) for pattern in patterns) for url in frontend_urls)
