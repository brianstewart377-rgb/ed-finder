from __future__ import annotations

import json
from pathlib import Path
import sys
import unicodedata

import pytest

ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / "apps" / "importer" / "src"
sys.path.insert(0, str(IMPORTER_SRC))

import v3_body_subtypes as sut  # noqa: E402


AUDITED_PLANET_VALUES = ['Ammonia world', 'Class I gas giant', 'Class II gas giant', 'Class III gas giant', 'Class IV gas giant', 'Class V gas giant', 'Earthlike body', 'Earth-like world', 'Gas giant with ammonia based life', 'Gas giant with ammonia-based life', 'Gas giant with water based life', 'Gas giant with water-based life', 'Helium gas giant', 'Helium rich gas giant', 'Helium-rich gas giant', 'High metal content body', 'High metal content world', 'Icy body', 'Metal rich body', 'Metal-rich body', 'Rocky body', 'Rocky ice body', 'Rocky Ice world', 'Sudarsky class I gas giant', 'Sudarsky class II gas giant', 'Sudarsky class III gas giant', 'Sudarsky class IV gas giant', 'Water giant', 'Water world']
AUDITED_STAR_VALUES = ['A (Blue-White) Star', 'A (Blue-White super giant) Star', 'B (Blue-White) Star', 'B (Blue-White super giant) Star', 'Black Hole', 'CJ Star', 'CN Star', 'C Star', 'F (White) Star', 'F (White super giant) Star', 'G (White-Yellow) Star', 'G (White-Yellow super giant) Star', 'Herbig Ae/Be Star', 'K (Yellow-Orange giant) Star', 'K (Yellow-Orange) Star', 'L (Brown dwarf) Star', 'M', 'M (Red dwarf) Star', 'M (Red giant) Star', 'M (Red super giant) Star', 'MS-type Star', 'N', 'Neutron Star', 'O (Blue-White) Star', 'S-type Star', 'Supermassive Black Hole', 'T (Brown dwarf) Star', 'T Tauri Star', 'White Dwarf (DAB) Star', 'White Dwarf (DA) Star', 'White Dwarf (DAV) Star', 'White Dwarf (DAZ) Star', 'White Dwarf (DB) Star', 'White Dwarf (DBV) Star', 'White Dwarf (DBZ) Star', 'White Dwarf (DC) Star', 'White Dwarf (DCV) Star', 'White Dwarf (DQ) Star', 'White Dwarf (D) Star', 'Wolf-Rayet C Star', 'Wolf-Rayet NC Star', 'Wolf-Rayet N Star', 'Wolf-Rayet O Star', 'Wolf-Rayet Star', 'Y', 'Y (Brown dwarf) Star']
AUDITED_VALUES = [
    *(("planet", value) for value in AUDITED_PLANET_VALUES),
    *(("star", value) for value in AUDITED_STAR_VALUES),
]
EXPECTED_UNRESOLVED = {"M", "N", "Y"}
EXPECTED_MANIFEST_SHA256 = "1a4b19585c9e20a73a4e93ea54078c18696456f1b41bef540eef0aae150c1662"


def _resolved(source: str, body_type: str, value: object):
    return sut.resolve_body_subtype(source, body_type, value)


def _manifest():
    return json.loads((IMPORTER_SRC / "body_subtypes_v1.json").read_text(encoding="utf-8"))


def _norm(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def test_manifest_revision_and_cardinality_are_exact():
    manifest = _manifest()
    assert manifest["manifest_revision"] == "v3-body-subtype-map-1"
    assert len(manifest["canonical_entries"]) == 61
    assert sum(e["body_type_code"] == "planet" for e in manifest["canonical_entries"]) == 18
    assert sum(e["body_type_code"] == "star" for e in manifest["canonical_entries"]) == 43
    assert [e.body_subtype_id for e in sut.canonical_entries()[:18]] == list(range(1001, 1019))
    assert [e.body_subtype_id for e in sut.canonical_entries()[18:]] == list(range(2001, 2044))


def test_manifest_ids_public_codes_and_aliases_are_unique():
    entries = _manifest()["canonical_entries"]
    ids = [e["body_subtype_id"] for e in entries]
    codes = [e["public_code"] for e in entries]
    assert len(ids) == len(set(ids))
    assert len(codes) == len(set(codes))
    per_domain = set()
    for entry in entries:
        sources = ["spansh_subtype", "legacy_subtype_inventory"]
        if entry["body_type_code"] == "planet":
            sources.append("frontier_planet_class")
        for alias in entry["aliases"]:
            assert alias.strip()
            for source in sources:
                key = (source, entry["body_type_code"], _norm(alias))
                assert key not in per_domain
                per_domain.add(key)


def test_all_75_audited_source_values_are_accounted_for():
    assert len(AUDITED_VALUES) == 75
    results = [
        _resolved("legacy_subtype_inventory", body_type, value)
        for body_type, value in AUDITED_VALUES
    ]
    assert all(result.disposition in {"resolved", "explicit_unresolved"} for result in results)


def test_exactly_72_audited_values_resolve():
    results = [
        _resolved("legacy_subtype_inventory", body_type, value)
        for body_type, value in AUDITED_VALUES
    ]
    assert sum(result.disposition == "resolved" for result in results) == 72
    assert sum(result.disposition == "explicit_unresolved" for result in results) == 3


def test_exactly_m_n_y_are_explicitly_unresolved():
    unresolved = {
        value
        for body_type, value in AUDITED_VALUES
        if _resolved("legacy_subtype_inventory", body_type, value).disposition
        == "explicit_unresolved"
    }
    assert unresolved == EXPECTED_UNRESOLVED


def test_hmc_world_and_body_aliases_resolve_same_identity():
    a = _resolved("spansh_subtype", "planet", "High metal content world")
    b = _resolved("spansh_subtype", "planet", "High metal content body")
    assert a.disposition == b.disposition == "resolved"
    assert a.body_subtype_id == b.body_subtype_id == 1002
    assert a.public_code == b.public_code == "high_metal_content_world"


def test_metal_rich_aliases_resolve_same_identity():
    a = _resolved("spansh_subtype", "planet", "Metal-rich body")
    b = _resolved("spansh_subtype", "planet", "Metal rich body")
    assert a.body_subtype_id == b.body_subtype_id == 1001


def test_rocky_ice_aliases_resolve_same_identity():
    a = _resolved("spansh_subtype", "planet", "Rocky Ice world")
    b = _resolved("spansh_subtype", "planet", "Rocky ice body")
    assert a.body_subtype_id == b.body_subtype_id == 1004


def test_earthlike_aliases_resolve_same_identity():
    a = _resolved("spansh_subtype", "planet", "Earth-like world")
    b = _resolved("spansh_subtype", "planet", "Earthlike body")
    assert a.body_subtype_id == b.body_subtype_id == 1007


@pytest.mark.parametrize(
    ("roman", "subtype_id"),
    [("I", 1010), ("II", 1011), ("III", 1012), ("IV", 1013)],
)
def test_sudarsky_aliases_resolve_to_same_gas_giant_classes(roman, subtype_id):
    modern = _resolved("spansh_subtype", "planet", f"Class {roman} gas giant")
    sudarsky = _resolved("spansh_subtype", "planet", f"Sudarsky class {roman} gas giant")
    assert modern.body_subtype_id == sudarsky.body_subtype_id == subtype_id


@pytest.mark.parametrize(
    ("hyphenated", "plain", "subtype_id"),
    [
        (
            "Gas giant with water-based life",
            "Gas giant with water based life",
            1015,
        ),
        (
            "Gas giant with ammonia-based life",
            "Gas giant with ammonia based life",
            1016,
        ),
    ],
)
def test_gas_giant_life_hyphen_variants_resolve_same_identity(
    hyphenated, plain, subtype_id
):
    a = _resolved("spansh_subtype", "planet", hyphenated)
    b = _resolved("spansh_subtype", "planet", plain)
    assert a.body_subtype_id == b.body_subtype_id == subtype_id


def test_helium_rich_hyphen_variant_resolves_same_identity():
    a = _resolved("spansh_subtype", "planet", "Helium-rich gas giant")
    b = _resolved("spansh_subtype", "planet", "Helium rich gas giant")
    assert a.body_subtype_id == b.body_subtype_id == 1018


def test_true_ammonia_world_requires_exact_class_alias():
    exact = _resolved("spansh_subtype", "planet", "Ammonia world")
    punctuation_guess = _resolved("spansh_subtype", "planet", "Ammonia-world")
    atmosphere_like = _resolved("spansh_subtype", "planet", "Ammonia atmosphere")
    assert exact.disposition == "resolved"
    assert exact.public_code == "ammonia_world"
    assert punctuation_guess.disposition == "unmapped"
    assert atmosphere_like.disposition == "unmapped"


def test_ammonia_gas_giant_is_not_ammonia_world():
    result = _resolved(
        "spansh_subtype", "planet", "Gas giant with ammonia-based life"
    )
    assert result.disposition == "resolved"
    assert result.public_code == "gas_giant_ammonia_life"
    assert result.public_code != "ammonia_world"


def test_unknown_nonempty_string_is_unmapped_not_guessed():
    result = _resolved("spansh_subtype", "planet", "Very metal-ish terraformable world")
    assert result.disposition == "unmapped"
    assert result.body_subtype_id is None
    assert result.public_code is None


@pytest.mark.parametrize("value", [None, "", "   ", "\t\n"])
def test_missing_and_blank_are_source_absent(value):
    result = _resolved("spansh_subtype", "planet", value)
    assert result.disposition == "source_absent"
    assert result.body_subtype_id is None


def test_lookup_is_case_insensitive_but_not_punctuation_inferential():
    case_variant = _resolved("spansh_subtype", "planet", "  wAtEr WoRlD  ")
    punctuation_variant = _resolved("spansh_subtype", "planet", "Water-world")
    assert case_variant.disposition == "resolved"
    assert case_variant.public_code == "water_world"
    assert punctuation_variant.disposition == "unmapped"


def test_planet_alias_on_star_body_is_type_mismatch():
    result = _resolved("spansh_subtype", "star", "Water world")
    assert result.disposition == "type_mismatch"


def test_star_alias_on_planet_body_is_type_mismatch():
    result = _resolved("spansh_subtype", "planet", "Neutron Star")
    assert result.disposition == "type_mismatch"


def test_frontier_planet_class_rejects_star_aliases():
    result = _resolved("frontier_planet_class", "planet", "Neutron Star")
    assert result.disposition == "type_mismatch"
    wrong_body = _resolved("frontier_planet_class", "star", "Water world")
    assert wrong_body.disposition == "type_mismatch"


def test_frontier_star_type_is_not_supported_by_v1_mapper():
    with pytest.raises(ValueError, match="unsupported body subtype source kind"):
        sut.resolve_body_subtype("frontier_star_type", "star", "N")  # type: ignore[arg-type]


@pytest.mark.parametrize("source", ["spansh_subtype", "legacy_subtype_inventory"])
@pytest.mark.parametrize("value", ["M", "N", "Y"])
def test_bare_m_n_y_never_resolve_from_legacy_or_spansh_source(source, value):
    result = _resolved(source, "star", value)
    assert result.disposition == "explicit_unresolved"
    assert result.body_subtype_id is None


def test_modifiers_are_not_present_in_canonical_subtype_manifest():
    codes = {entry.public_code for entry in sut.canonical_entries()}
    banned = {
        "geological",
        "biological",
        "ringed",
        "terraformable",
        "volcanism",
        "atmosphere",
        "landable",
    }
    assert not codes.intersection(banned)
    assert _resolved(
        "spansh_subtype", "planet", "High metal content world geological"
    ).disposition == "unmapped"


def test_repeated_resolution_is_byte_stable():
    payloads = {
        sut.resolution_canonical_json(
            _resolved("spansh_subtype", "planet", "High metal content body")
        )
        for _ in range(100)
    }
    assert len(payloads) == 1


def test_manifest_canonical_json_digest_is_stable():
    assert sut.canonical_manifest_sha256() == EXPECTED_MANIFEST_SHA256
    assert (
        sut.canonical_manifest_sha256()
        == __import__("hashlib").sha256(sut.canonical_manifest_bytes()).hexdigest()
    )


def test_all_canonical_aliases_resolve_for_supported_domains():
    manifest = _manifest()
    for entry in manifest["canonical_entries"]:
        body_type = entry["body_type_code"]
        for alias in entry["aliases"]:
            for source in ("spansh_subtype", "legacy_subtype_inventory"):
                result = _resolved(source, body_type, alias)
                assert result.disposition == "resolved"
                assert result.body_subtype_id == entry["body_subtype_id"]
            if body_type == "planet":
                frontier = _resolved("frontier_planet_class", "planet", alias)
                assert frontier.disposition == "resolved"
                assert frontier.body_subtype_id == entry["body_subtype_id"]


def test_legacy_inventory_is_not_a_production_lineage():
    assert sut.is_production_source_kind("spansh_subtype")
    assert sut.is_production_source_kind("frontier_planet_class")
    assert not sut.is_production_source_kind("legacy_subtype_inventory")


def test_non_string_non_null_values_are_unmapped():
    for value in [42, 3.14, True, {"class": "Water world"}, ["Water world"]]:
        result = _resolved("spansh_subtype", "planet", value)
        assert result.disposition == "unmapped"
        assert result.body_subtype_id is None
