"""Contracts for packaging the deployable V3 Svelte image."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "apps" / "web" / "Dockerfile"
PARITY_WORKFLOW = ROOT / ".github" / "workflows" / "container-image-parity.yml"

NODE_IMAGE = (
    "FROM node:24-alpine@sha256:"
    "e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf AS build"
)
NGINX_IMAGE = (
    "FROM nginx:1.29-alpine@sha256:"
    "5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de AS runtime"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_web_image_supplies_complete_local_packages_before_frozen_install() -> None:
    dockerfile = _read(DOCKERFILE)
    web_package = json.loads(_read(ROOT / "apps" / "web" / "package.json"))
    api_package = json.loads(
        _read(ROOT / "packages" / "api-client" / "package.json")
    )

    assert web_package["dependencies"]["@ed-finder/api-client"] == (
        "file:../../packages/api-client"
    )
    assert api_package["files"] == ["src"]
    assert api_package["exports"]["."]["import"] == "./src/index.ts"

    api_copy = "COPY packages/api-client/ /workspace/packages/api-client/"
    planner_copy = "COPY packages/planner-core/ /workspace/packages/planner-core/"
    frozen_install = "RUN pnpm install --frozen-lockfile"

    assert "/workspace/apps/web" in dockerfile
    assert dockerfile.index(api_copy) < dockerfile.index(frozen_install)
    assert dockerfile.index(planner_copy) < dockerfile.index(frozen_install)

    for package in ("api-client", "planner-core"):
        package_root = ROOT / "packages" / package
        assert (package_root / "package.json").is_file()
        assert (package_root / "tsconfig.json").is_file()
        assert (package_root / "tsconfig.build.json").is_file()
        assert (package_root / "src").is_dir()


def test_web_image_builds_shared_packages_in_dependency_order_before_svelte() -> None:
    dockerfile = _read(DOCKERFILE)
    web_package = json.loads(_read(ROOT / "apps" / "web" / "package.json"))
    planner_build_config = _read(
        ROOT / "packages" / "planner-core" / "tsconfig.build.json"
    )

    shared_build = web_package["scripts"]["shared:build"]
    assert shared_build.index("api-client/tsconfig.build.json") < shared_build.index(
        "planner-core/tsconfig.build.json"
    )
    assert "../api-client/dist/index.d.ts" in planner_build_config

    frozen_install = "RUN pnpm install --frozen-lockfile"
    shared_build_run = "RUN pnpm run shared:build"
    svelte_build = 'RUN VITE_BUILD_SHA="$BUILD_SHA" pnpm build'
    assert dockerfile.index(frozen_install) < dockerfile.index(shared_build_run)
    assert dockerfile.index(shared_build_run) < dockerfile.index(svelte_build)


def test_web_image_retains_locked_release_and_static_delivery_contract() -> None:
    dockerfile = _read(DOCKERFILE)

    assert NODE_IMAGE in dockerfile
    assert NGINX_IMAGE in dockerfile
    assert "ENV CYPRESS_INSTALL_BINARY=0" in dockerfile
    assert "corepack prepare pnpm@11.25.0 --activate" in dockerfile
    assert dockerfile.count("RUN pnpm install --frozen-lockfile") == 1
    assert dockerfile.count("ARG BUILD_SHA") == 2
    assert dockerfile.count("[ \"${#BUILD_SHA}\" -eq 40 ]") == 2
    assert 'LABEL org.opencontainers.image.revision="$BUILD_SHA"' in dockerfile
    assert (
        "COPY --from=build /workspace/apps/web/build/ /usr/share/nginx/html/"
        in dockerfile
    )
    assert 'NGINX_ENVSUBST_FILTER="^EDFINDER_API_UPSTREAM$"' in dockerfile


def test_protected_parity_lane_builds_the_real_web_image_without_publishing() -> None:
    workflow = _read(PARITY_WORKFLOW)
    pull_request = workflow.split("  pull_request:", 1)[1].split("  push:", 1)[0]
    push = workflow.split("  push:", 1)[1].split("  schedule:", 1)[0]
    parity_job = workflow.split("  parity:\n", 1)[1]
    web_build_step = parity_job.split(
        "      - name: Build deployable Svelte web image\n", 1
    )[1].split("      - name:", 1)[0]

    assert "paths:" not in pull_request
    for path in (
        "apps/web/**",
        "packages/api-client/**",
        "packages/planner-core/**",
        ".dockerignore",
        "tests/test_v3_web_release_image.py",
    ):
        assert f"- '{path}'" in push

    assert "runs-on: ubuntu-latest" in parity_job
    assert "context: ." in web_build_step
    assert "file: apps/web/Dockerfile" in web_build_step
    assert "platforms: linux/amd64" in web_build_step
    assert "load: true" in web_build_step
    assert "push: false" in web_build_step
    assert "BUILD_SHA=${{ github.sha }}" in web_build_step
    assert "docker/login-action" not in parity_job
    assert "packages: write" not in parity_job
    assert "tests/test_v3_web_release_image.py -q" in parity_job
    assert "org.opencontainers.image.revision" in parity_job
    assert "/usr/share/nginx/html/index.html" in parity_job
    assert "/usr/share/nginx/html/200.html" in parity_job
