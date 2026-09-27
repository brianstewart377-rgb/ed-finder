"""V3 Finder ranking-profile identity (F2c, Task 1).

Pure, DB-free identity for the versioned ranking profile that turns the V3
derived projections (`v3_app.system_search`, `v3_app.system_archetype`,
`v3_app.system_archetype_summary`) into an ordering. This module holds
**identity only**:

- `RANKING_VERSION` — the current profile's version string.
- `PROFILE_SPEC` — the canonical, hashable ranking definition (primary-score
  rule, uncertainty modifier, tie-break, tier thresholds, hard-filter keys,
  archetype keys) plus its own recorded `ranking_sha256`.
- `ranking_sha256()` — recomputes the sha256 of the canonical spec so a
  drift-guard test can assert the recorded value never silently diverges
  from the live definition.
- `RANKING_VERSIONS` / `resolve()` — a small registry so routers select a
  version rather than hand-writing ranking logic.

No database access and no SQL live here — the parameterized-SQL builder
that consumes this spec is a separate, later task (F2c Task 2). Pure
stdlib only (`hashlib`, `json`).

See docs/superpowers/specs/2026-09-27-v3-finder-f2c-f3-ranking-design.md and
docs/superpowers/plans/2026-09-27-v3-finder-f2c-f3-ranking.md (Task 1).
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any, Final

RANKING_VERSION: Final[str] = "v3-colony-potential-1"

# The 8 V3-native archetype keys computed by F2b (scripts/v3_system_archetype_
# model.py's `ARCHETYPE_KEYS` is the source of truth). Duplicated here as a
# plain literal rather than imported: the deployed API image only ships
# `apps/api/src/` (see apps/api/Dockerfile), not the repo-root `scripts/`
# tree, and this module must stay pure/DB-free with no cross-tree coupling.
# Keep in sync if the archetype set ever changes.
ARCHETYPE_KEYS: Final[tuple[str, ...]] = (
    "paradise",
    "mining_hub",
    "manufacturing_hub",
    "megacomplex",
    "research_hub",
    "stronghold",
    "population_capital",
    "flexible",
)

# Tier thresholds from the F2b projection contract: S>=88, A>=76, B>=60,
# C>=45, else D.
TIER_THRESHOLDS: Final[dict[str, int]] = {"S": 88, "A": 76, "B": 60, "C": 45}

# Hard filters are applied first, before any score/order computation, and
# never gate on uncertainty (unknown != absent). Keys mirror the F1
# `system_search` facts + body-type counts plus the distance/region bounds
# from `docs/superpowers/specs/2026-09-27-v3-finder-f2c-f3-ranking-design.md`.
HARD_FILTER_KEYS: Final[tuple[str, ...]] = (
    "elw_count_min",
    "ww_count_min",
    "terraformable_count_min",
    "landable_count_min",
    "has_rings",
    "min_development_score",
    "max_distance_ly",
    "galaxy_region",
)

# Tie-break order applied after the primary score x uncertainty ordering:
# nearest reference distance first, then system_id64 for determinism.
TIE_BREAK: Final[tuple[str, ...]] = ("distance", "system_id64")


def _json(value: Any) -> str:
    """Canonical JSON encoding.

    Mirrors the `_json`/hashing style in `scripts/v3_system_archetype.py`:
    sorted keys, compact separators, ASCII-safe, no NaN/Infinity — so the
    same logical spec always serialises to the same bytes.
    """

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _canonical_base() -> dict[str, Any]:
    """The canonical ranking spec, excluding its own recorded sha.

    This is the single source of truth both `PROFILE_SPEC` and
    `ranking_sha256()`'s default hash are built from, so the two can never
    drift apart by construction.
    """

    return {
        "ranking_version": RANKING_VERSION,
        "primary_score_rule": {
            "archetype": "system_archetype.archetype_score",
            "economy": "potential_score",
            "none": "system_archetype_summary.best_colony_potential",
        },
        "uncertainty": {
            # Soft modifier only (unknown != absent) — never a hard filter.
            # Starting curve is the plain product of confidence and
            # completeness; both bounded [0, 1]. This curve is a tunable,
            # benchmark-calibrated profile parameter and is part of the
            # hashed identity, so any future retune bumps ranking_sha256.
            "factor_expr": "confidence * completeness",
            "confidence_range": [0.0, 1.0],
            "completeness_range": [0.0, 1.0],
        },
        "tie_break": list(TIE_BREAK),
        "tier_thresholds": dict(TIER_THRESHOLDS),
        "hard_filter_keys": list(HARD_FILTER_KEYS),
        "archetype_keys": list(ARCHETYPE_KEYS),
    }


def ranking_sha256(spec: Mapping[str, Any] | None = None) -> str:
    """sha256 hex digest of a canonicalized ranking spec.

    Excludes the spec's own `ranking_sha256` field (a spec can't hash
    itself). With no argument, hashes the live `_canonical_base()` — the
    drift guard: `ranking_sha256() == PROFILE_SPEC["ranking_sha256"]` must
    always hold. Accepts an explicit spec-shaped mapping so callers (tests)
    can hash an arbitrary/mutated spec, e.g. to prove the guard would catch
    a silent definition change.
    """

    source = _canonical_base() if spec is None else spec
    payload = {key: value for key, value in source.items() if key != "ranking_sha256"}
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


PROFILE_SPEC: Final[dict[str, Any]] = {
    **_canonical_base(),
    "ranking_sha256": ranking_sha256(),
}

RANKING_VERSIONS: Final[dict[str, dict[str, Any]]] = {
    RANKING_VERSION: PROFILE_SPEC,
}


def resolve(version: str) -> dict[str, Any]:
    """Resolve a `ranking_version` string to its frozen `PROFILE_SPEC`.

    Raises `KeyError` for an unknown version — callers (routers) turn this
    into a 4xx rather than silently falling back to a different profile.
    """

    try:
        return RANKING_VERSIONS[version]
    except KeyError as exc:
        raise KeyError(f"Unknown ranking_version: {version!r}") from exc
