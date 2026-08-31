"""Deterministic explicit-source body-subtype mapper for normalized V3.

This module intentionally performs *identity lookup only*. It does not infer body
subtype from atmosphere, composition, signals, volcanism, terraformability, or
any other mechanic/modifier.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import unicodedata
from typing import Literal, cast

SourceKind = Literal[
    "spansh_subtype",
    "frontier_planet_class",
    "legacy_subtype_inventory",
]
BodyTypeCode = Literal["star", "planet", "barycentre", "belt_cluster"]
SubtypeDisposition = Literal[
    "resolved",
    "source_absent",
    "explicit_unresolved",
    "unmapped",
    "type_mismatch",
]

MANIFEST_REVISION = "v3-body-subtype-map-1"
_MANIFEST_PATH = Path(__file__).with_name("body_subtypes_v1.json")
_SUPPORTED_SOURCE_KINDS = frozenset(
    {"spansh_subtype", "frontier_planet_class", "legacy_subtype_inventory"}
)
_SUPPORTED_BODY_TYPES = frozenset({"star", "planet", "barycentre", "belt_cluster"})
_PRODUCTION_SOURCE_KINDS = frozenset({"spansh_subtype", "frontier_planet_class"})
_BANNED_MODIFIER_CODES = frozenset(
    {
        "geological",
        "biological",
        "ringed",
        "terraformable",
        "volcanism",
        "atmosphere",
        "landable",
    }
)


@dataclass(frozen=True)
class CanonicalBodySubtype:
    body_subtype_id: int
    body_type_code: Literal["star", "planet"]
    public_code: str
    display_name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class BodySubtypeResolution:
    source_kind: SourceKind
    raw_value: str | None
    normalized_lookup_value: str | None
    body_type_code: BodyTypeCode
    disposition: SubtypeDisposition
    body_subtype_id: int | None
    public_code: str | None
    display_name: str | None
    manifest_revision: str


def _normalize_lookup(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _read_manifest() -> dict:
    with _MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("body subtype manifest must be a JSON object")
    return data


def _entry_from_raw(raw: object) -> CanonicalBodySubtype:
    if not isinstance(raw, dict):
        raise ValueError("canonical subtype entry must be an object")

    subtype_id = raw.get("body_subtype_id")
    body_type = raw.get("body_type_code")
    public_code = raw.get("public_code")
    display_name = raw.get("display_name")
    aliases = raw.get("aliases")

    if not isinstance(subtype_id, int) or isinstance(subtype_id, bool):
        raise ValueError("body_subtype_id must be an integer")
    if subtype_id < -32768 or subtype_id > 32767:
        raise ValueError(f"body_subtype_id outside signed SMALLINT: {subtype_id}")
    if body_type not in {"star", "planet"}:
        raise ValueError(f"unsupported canonical body_type_code: {body_type!r}")
    if not isinstance(public_code, str) or not public_code.strip():
        raise ValueError("public_code must be a non-empty string")
    if not isinstance(display_name, str) or not display_name.strip():
        raise ValueError("display_name must be a non-empty string")
    if not isinstance(aliases, list) or not aliases:
        raise ValueError(f"aliases must be a non-empty list for {public_code}")
    if any(not isinstance(alias, str) or not alias.strip() for alias in aliases):
        raise ValueError(f"every alias must be non-empty for {public_code}")

    return CanonicalBodySubtype(
        body_subtype_id=subtype_id,
        body_type_code=cast(Literal["star", "planet"], body_type),
        public_code=public_code,
        display_name=display_name,
        aliases=tuple(aliases),
    )


def _validate_and_compile_manifest(data: dict):
    if data.get("manifest_revision") != MANIFEST_REVISION:
        raise ValueError(
            f"unexpected body subtype manifest revision: {data.get('manifest_revision')!r}"
        )

    raw_entries = data.get("canonical_entries")
    if not isinstance(raw_entries, list):
        raise ValueError("canonical_entries must be a list")
    entries = tuple(_entry_from_raw(raw) for raw in raw_entries)

    if len(entries) != 61:
        raise ValueError(f"expected exactly 61 canonical subtypes, got {len(entries)}")

    planets = tuple(entry for entry in entries if entry.body_type_code == "planet")
    stars = tuple(entry for entry in entries if entry.body_type_code == "star")
    if len(planets) != 18 or len(stars) != 43:
        raise ValueError(
            f"expected 18 planet and 43 star subtypes, got {len(planets)} and {len(stars)}"
        )
    if {entry.body_subtype_id for entry in planets} != set(range(1001, 1019)):
        raise ValueError("planet subtype IDs must be exactly 1001..1018")
    if {entry.body_subtype_id for entry in stars} != set(range(2001, 2044)):
        raise ValueError("star subtype IDs must be exactly 2001..2043")

    ids = [entry.body_subtype_id for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("body_subtype_id values must be unique")
    public_codes = [entry.public_code for entry in entries]
    if len(public_codes) != len(set(public_codes)):
        raise ValueError("public_code values must be unique")
    if _BANNED_MODIFIER_CODES.intersection(public_codes):
        raise ValueError("modifier identity found in canonical body subtype manifest")

    explicit_unresolved = data.get("explicit_unresolved")
    if explicit_unresolved != {
        "spansh_subtype": ["M", "N", "Y"],
        "legacy_subtype_inventory": ["M", "N", "Y"],
    }:
        raise ValueError("explicit_unresolved set must be exactly M/N/Y for spansh and legacy")

    alias_lookup: dict[tuple[str, str, str], CanonicalBodySubtype] = {}
    alias_types: dict[tuple[str, str], set[str]] = {}
    all_alias_types: dict[str, set[str]] = {}

    for entry in entries:
        applicable_sources = {"spansh_subtype", "legacy_subtype_inventory"}
        if entry.body_type_code == "planet":
            applicable_sources.add("frontier_planet_class")
        for alias in entry.aliases:
            normalized = _normalize_lookup(alias)
            if not normalized:
                raise ValueError(f"empty normalized alias for {entry.public_code}")
            all_alias_types.setdefault(normalized, set()).add(entry.body_type_code)
            for source_kind in applicable_sources:
                key = (source_kind, entry.body_type_code, normalized)
                prior = alias_lookup.get(key)
                if prior is not None and prior.body_subtype_id != entry.body_subtype_id:
                    raise ValueError(
                        f"alias collision for {source_kind}/{entry.body_type_code}: {alias!r}"
                    )
                alias_lookup[key] = entry
                alias_types.setdefault((source_kind, normalized), set()).add(
                    entry.body_type_code
                )

    unresolved_lookup: dict[str, frozenset[str]] = {}
    for source_kind, values in explicit_unresolved.items():
        normalized_values = frozenset(_normalize_lookup(value) for value in values)
        if len(normalized_values) != len(values):
            raise ValueError(f"duplicate explicit unresolved alias for {source_kind}")
        for normalized in normalized_values:
            if alias_types.get((source_kind, normalized)):
                raise ValueError(
                    f"explicit unresolved token collides with resolved alias: "
                    f"{source_kind}/{normalized}"
                )
        unresolved_lookup[source_kind] = normalized_values

    return (
        entries,
        alias_lookup,
        alias_types,
        all_alias_types,
        unresolved_lookup,
    )


_MANIFEST = _read_manifest()
(
    _CANONICAL_ENTRIES,
    _ALIAS_LOOKUP,
    _ALIAS_TYPES,
    _ALL_ALIAS_TYPES,
    _UNRESOLVED_LOOKUP,
) = _validate_and_compile_manifest(_MANIFEST)


def canonical_entries() -> tuple[CanonicalBodySubtype, ...]:
    """Return the immutable, ID-ordered canonical subtype registry."""
    return tuple(sorted(_CANONICAL_ENTRIES, key=lambda entry: entry.body_subtype_id))


def canonical_manifest_json() -> str:
    """Return canonical JSON serialization of the authoritative manifest."""
    return json.dumps(
        _MANIFEST,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_manifest_bytes() -> bytes:
    return canonical_manifest_json().encode("utf-8")


def canonical_manifest_sha256() -> str:
    return sha256(canonical_manifest_bytes()).hexdigest()


def is_production_source_kind(source_kind: str) -> bool:
    """Whether a source kind is allowed as future canonical generation lineage."""
    return source_kind in _PRODUCTION_SOURCE_KINDS


def resolve_body_subtype(
    source_kind: SourceKind,
    body_type_code: BodyTypeCode,
    raw_value: object,
) -> BodySubtypeResolution:
    """Resolve one explicit subtype value without semantic inference."""
    if source_kind not in _SUPPORTED_SOURCE_KINDS:
        raise ValueError(f"unsupported body subtype source kind: {source_kind!r}")
    if body_type_code not in _SUPPORTED_BODY_TYPES:
        raise ValueError(f"unsupported body type code: {body_type_code!r}")

    typed_source = cast(SourceKind, source_kind)
    typed_body_type = cast(BodyTypeCode, body_type_code)

    if raw_value is None:
        return BodySubtypeResolution(
            source_kind=typed_source,
            raw_value=None,
            normalized_lookup_value=None,
            body_type_code=typed_body_type,
            disposition="source_absent",
            body_subtype_id=None,
            public_code=None,
            display_name=None,
            manifest_revision=MANIFEST_REVISION,
        )

    if not isinstance(raw_value, str):
        return BodySubtypeResolution(
            source_kind=typed_source,
            raw_value=None,
            normalized_lookup_value=None,
            body_type_code=typed_body_type,
            disposition="unmapped",
            body_subtype_id=None,
            public_code=None,
            display_name=None,
            manifest_revision=MANIFEST_REVISION,
        )

    normalized = _normalize_lookup(raw_value)
    if not normalized:
        return BodySubtypeResolution(
            source_kind=typed_source,
            raw_value=raw_value,
            normalized_lookup_value=None,
            body_type_code=typed_body_type,
            disposition="source_absent",
            body_subtype_id=None,
            public_code=None,
            display_name=None,
            manifest_revision=MANIFEST_REVISION,
        )

    if normalized in _UNRESOLVED_LOOKUP.get(source_kind, frozenset()):
        return BodySubtypeResolution(
            source_kind=typed_source,
            raw_value=raw_value,
            normalized_lookup_value=normalized,
            body_type_code=typed_body_type,
            disposition="explicit_unresolved",
            body_subtype_id=None,
            public_code=None,
            display_name=None,
            manifest_revision=MANIFEST_REVISION,
        )

    if source_kind == "frontier_planet_class" and body_type_code != "planet":
        return BodySubtypeResolution(
            source_kind=typed_source,
            raw_value=raw_value,
            normalized_lookup_value=normalized,
            body_type_code=typed_body_type,
            disposition="type_mismatch",
            body_subtype_id=None,
            public_code=None,
            display_name=None,
            manifest_revision=MANIFEST_REVISION,
        )

    entry = _ALIAS_LOOKUP.get((source_kind, body_type_code, normalized))
    if entry is not None:
        return BodySubtypeResolution(
            source_kind=typed_source,
            raw_value=raw_value,
            normalized_lookup_value=normalized,
            body_type_code=typed_body_type,
            disposition="resolved",
            body_subtype_id=entry.body_subtype_id,
            public_code=entry.public_code,
            display_name=entry.display_name,
            manifest_revision=MANIFEST_REVISION,
        )

    source_alias_types = _ALIAS_TYPES.get((source_kind, normalized), set())
    if source_alias_types and body_type_code not in source_alias_types:
        disposition: SubtypeDisposition = "type_mismatch"
    elif source_kind == "frontier_planet_class" and _ALL_ALIAS_TYPES.get(normalized) == {"star"}:
        disposition = "type_mismatch"
    elif _ALL_ALIAS_TYPES.get(normalized) and body_type_code not in _ALL_ALIAS_TYPES[normalized]:
        disposition = "type_mismatch"
    else:
        disposition = "unmapped"

    return BodySubtypeResolution(
        source_kind=typed_source,
        raw_value=raw_value,
        normalized_lookup_value=normalized,
        body_type_code=typed_body_type,
        disposition=disposition,
        body_subtype_id=None,
        public_code=None,
        display_name=None,
        manifest_revision=MANIFEST_REVISION,
    )


def resolution_canonical_json(resolution: BodySubtypeResolution) -> str:
    """Stable serialized form used by determinism tests and evidence receipts."""
    return json.dumps(
        asdict(resolution),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
