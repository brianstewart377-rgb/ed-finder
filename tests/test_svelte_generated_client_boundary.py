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
def test_facade_delegates_ordinary_operations_to_generated_sdk_with_normalization():
    """Lock the intended V3 API boundary rather than merely accepting generated
    type imports plus handwritten raw-route operations.

    Ordinary API operations MUST delegate to the generated Hey API SDK
    operations; the facade layers the application normalization (lossless Id64,
    structured ApiError, same-origin credentials, bounded session-only admin
    token, system-envelope unwrapping) on top by configuring the generated
    client. The raw shared transport is NOT the operation lane for bootstrap
    operations any more.
    """
    source = FACADE.read_text(encoding="utf-8")
    transport = (
        ROOT / "packages" / "api-client" / "src" / "core.ts"
    ).read_text(encoding="utf-8")

    # Ordinary operations delegate to the GENERATED Hey API SDK operations.
    assert "from './generated/sdk.gen'" in source
    assert "healthApiHealthGet(" in source
    assert "authSessionApiAuthSessionGet(" in source
    assert "getSystemApiSystemId64Get(" in source
    assert "autocompleteApiLocalAutocompleteGet(" in source
    assert "localSearchEndpointApiLocalSearchPost(" in source

    # ...not the raw shared transport hand-rolling the route any more.
    assert "apiRequest('/health'" not in source
    assert "apiRequest('/auth/session'" not in source

    # The facade configures the generated client with the application transport
    # contract (same-origin credentials, interceptors) and keeps the generated
    # response TYPES for its public return types.
    assert "from './generated/client.gen'" in source
    assert "credentials: 'include'" in source
    assert "interceptors" in source
    assert "import type {" in source and "from './generated'" in source
    for generated_type in (
        "AuthSessionResponse",
        "HealthResponse",
        "AutocompleteHit",
        "LocalSearchRequest",
        "SearchResponse",
        "SystemDetailRow",
    ):
        assert generated_type in source

    # Application normalization stays a facade responsibility: lossless Id64
    # before unsafe number coercion, structured ApiError, system-envelope
    # unwrapping, and the shared normalization primitives from the api-client
    # core package.
    assert "from '@ed-finder/api-client/core'" in source
    assert "parseLosslessJson" in source
    assert "ApiError" in source
    assert "export async function getSystem" in source

    # The shared browser transport keeps the same lossless + credentialed
    # contract for the retained React migration-evidence consumer.
    assert "export async function apiRequest" in transport
    assert "parseLosslessJson" in transport
    assert "credentials: 'include'" in transport
