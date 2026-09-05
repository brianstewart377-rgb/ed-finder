import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WEB_SOURCE = ROOT / "apps" / "web" / "src"
FACADE = WEB_SOURCE / "lib" / "api" / "client.ts"
GENERATED = WEB_SOURCE / "lib" / "api" / "generated"
IMPORT_SPECIFIER = re.compile(
    r"(?:from\s+|import\s*\()\s*['\"]([^'\"]*generated(?:/[^'\"]*)?)['\"]"
)


@pytest.mark.unit
def test_generated_hey_api_modules_are_private_to_the_application_facade():
    violations: list[str] = []
    for path in WEB_SOURCE.rglob("*"):
        if not path.is_file() or path.suffix not in {".ts", ".js", ".svelte"}:
            continue
        if GENERATED in path.parents or path == FACADE or ".test." in path.name:
            continue
        source = path.read_text(encoding="utf-8")
        for match in IMPORT_SPECIFIER.finditer(source):
            violations.append(f"{path.relative_to(ROOT)} -> {match.group(1)}")

    assert not violations, (
        "Generated API modules must stay behind apps/web/src/lib/api/client.ts; "
        "id64-bearing responses require the lossless application facade:\n"
        + "\n".join(violations)
    )


@pytest.mark.unit
def test_facade_documents_and_implements_the_lossless_id64_lane():
    source = FACADE.read_text(encoding="utf-8")
    transport = (
        ROOT / "packages" / "api-client" / "src" / "core.ts"
    ).read_text(encoding="utf-8")

    assert "from '@ed-finder/api-client/core'" in source
    assert "export async function getSystem" in source
    assert (
        "import type { AuthSessionResponse, HealthResponse } from './generated'"
        in source
    )
    assert "apiRequest('/health', { signal })" in source
    assert "apiRequest('/auth/session', { signal })" in source
    assert "export async function apiRequest" in transport
    assert "parseLosslessJson" in transport
    assert "credentials: 'include'" in transport
