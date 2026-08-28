"""V3 journal-intelligence fixture contract tests (Task 7).

Drives every synthetic journal in ``tests/fixtures/journal_v3/`` through the
V3.0 event-identity contract (plan ``2026-08-28-v3-journal-intelligence-foundation.md``
Task 2 interfaces ``strip_payload`` / ``event_identity``) with a Python JSONL
reader that mimics the client worker's line discipline (``journalParser.ts``):

* lines are split on ``\\n``; a trailing segment without a newline is still a
  line (``parseFinalLine`` behaviour);
* blank lines are silently skipped;
* malformed JSON lines are skipped and counted as warnings;
* unknown / non-allowlisted event types are skipped as warnings, never raise;
* within-run duplicate lines (identical line content) collapse on the line
  SHA-256 hash.

The contract functions are imported from the real ``edfinder_api.journal``
modules when Task 2 has landed; until then a reference implementation of the
exact documented V3.0 interface lives in this module and ``CONTRACT_IMPL``
records which one ran.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "journal_v3"

# ---------------------------------------------------------------------------
# Contract functions: real Task 2 modules first, documented-interface
# reference implementation as fallback.
# ---------------------------------------------------------------------------

try:
    from edfinder_api.journal.event_contract import (  # type: ignore[import-not-found]
        EVENT_PAYLOAD_ALLOWLIST,
        JOURNAL_EVENT_ALLOWLIST,
        strip_payload as _contract_strip_payload,
    )
    from edfinder_api.journal.identity import (  # type: ignore[import-not-found]
        event_identity as _contract_event_identity,
    )

    CONTRACT_IMPL = "edfinder_api.journal (Task 2 implementation landed)"
    strip_payload = _contract_strip_payload
    event_identity = _contract_event_identity
except ImportError:
    _contract_strip_payload = None
    _contract_event_identity = None
    CONTRACT_IMPL = (
        "reference implementation of the plan V3.0 interface "
        "(edfinder_api.journal not landed when Task 7 ran)"
    )

    JOURNAL_EVENT_ALLOWLIST = frozenset(
        {
            "ApproachBody",
            "CarrierJump",
            "CodexEntry",
            "Commander",
            "Died",
            "Disembark",
            "Docked",
            "Embark",
            "Fileheader",
            "FSDJump",
            "FSDTarget",
            "FSSAllBodiesFound",
            "FSSBodySignals",
            "FSSDiscoveryScan",
            "LeaveBody",
            "Liftoff",
            "LoadGame",
            "Location",
            "MultiSellExplorationData",
            "NavRoute",
            "NavRouteClear",
            "Resurrect",
            "SAAScanComplete",
            "SAASignalsFound",
            "Scan",
            "ScanOrganic",
            "Screenshot",
            "SellExplorationData",
            "SellOrganicData",
            "Touchdown",
        }
    )

    # Mirrors the client parser's EVENT_PAYLOAD_FIELDS (journalParser.ts) plus
    # the plan's GameVersion/GameBuild attach fields on every event.
    _EVENT_PAYLOAD_FIELDS: dict[str, frozenset[str]] = {
        "ApproachBody": frozenset({"StarSystem", "SystemAddress", "Body", "BodyID", "BodyName"}),
        "CarrierJump": frozenset(
            {"StarSystem", "SystemAddress", "StarPos", "Body", "BodyID", "BodyType", "Docked"}
        ),
        "CodexEntry": frozenset(
            {
                "EntryID",
                "Name",
                "Name_Localised",
                "SubCategory",
                "SubCategory_Localised",
                "Category",
                "Category_Localised",
                "Region",
                "System",
                "SystemAddress",
                "BodyID",
                "NearestDestination",
                "NearestDestination_Localised",
                "Latitude",
                "Longitude",
                "Traits",
            }
        ),
        "Commander": frozenset({"Name", "FID"}),
        "Died": frozenset({"KillerName", "KillerShip", "KillerRank", "Killers"}),
        "Disembark": frozenset(
            {"SRV", "Taxi", "Multicrew", "StarSystem", "SystemAddress", "Body", "BodyID", "BodyName", "OnStation", "OnPlanet"}
        ),
        "Docked": frozenset(
            {
                "StarSystem",
                "SystemAddress",
                "StationName",
                "StationType",
                "MarketID",
                "DistFromStarLS",
                "StationGovernment",
                "StationAllegiance",
                "StationServices",
                "StationEconomies",
                "Taxi",
                "Multicrew",
            }
        ),
        "Embark": frozenset(
            {"SRV", "Taxi", "Multicrew", "StarSystem", "SystemAddress", "Body", "BodyID", "BodyName", "OnStation", "OnPlanet"}
        ),
        "Fileheader": frozenset({"part", "language", "Odyssey", "gameversion", "build"}),
        "FSDJump": frozenset(
            {"StarSystem", "SystemAddress", "StarPos", "StarClass", "JumpDist", "FuelUsed", "FuelLevel"}
        ),
        "FSDTarget": frozenset({"Name", "SystemAddress", "StarClass", "RemainingJumpsInRoute"}),
        "FSSAllBodiesFound": frozenset({"StarSystem", "SystemAddress", "Count"}),
        "FSSBodySignals": frozenset({"StarSystem", "SystemAddress", "BodyName", "BodyID", "Signals"}),
        "FSSDiscoveryScan": frozenset(
            {"StarSystem", "SystemAddress", "Progress", "BodyCount", "NonBodyCount"}
        ),
        "LeaveBody": frozenset({"StarSystem", "SystemAddress", "Body", "BodyID", "BodyName"}),
        "Liftoff": frozenset(
            {
                "StarSystem",
                "SystemAddress",
                "Body",
                "BodyID",
                "BodyName",
                "Latitude",
                "Longitude",
                "PlayerControlled",
                "NearestDestination",
                "NearestDestination_Localised",
            }
        ),
        "LoadGame": frozenset(
            {
                "Commander",
                "FID",
                "Horizons",
                "Odyssey",
                "Ship",
                "Ship_Localised",
                "ShipID",
                "ShipName",
                "ShipIdent",
                "FuelLevel",
                "FuelCapacity",
                "GameMode",
                "Group",
                "Credits",
                "Loan",
            }
        ),
        "Location": frozenset(
            {
                "StarSystem",
                "StarPos",
                "Body",
                "BodyID",
                "BodyType",
                "Docked",
                "StationName",
                "StationType",
                "MarketID",
                "Latitude",
                "Longitude",
                "SystemAddress",
            }
        ),
        "MultiSellExplorationData": frozenset({"Discovered", "BaseValue", "Bonus", "TotalEarnings"}),
        "NavRoute": frozenset({"Route"}),
        "NavRouteClear": frozenset(),
        "Resurrect": frozenset({"Option", "Cost", "Bankrupt"}),
        "SAAScanComplete": frozenset({"SystemAddress", "BodyName", "BodyID", "ProbesUsed", "EfficiencyTarget"}),
        "SAASignalsFound": frozenset({"StarSystem", "SystemAddress", "BodyName", "BodyID", "Signals", "Genuses"}),
        "Scan": frozenset(
            {
                "ScanType",
                "StarSystem",
                "SystemAddress",
                "BodyName",
                "BodyID",
                "DistanceFromArrivalLS",
                "StarType",
                "Subclass",
                "StellarMass",
                "Radius",
                "AbsoluteMagnitude",
                "Age_MY",
                "SurfaceTemperature",
                "Luminosity",
                "SemiMajorAxis",
                "Eccentricity",
                "OrbitalInclination",
                "Periapsis",
                "OrbitalPeriod",
                "RotationPeriod",
                "AxialTilt",
                "Rings",
                "Parents",
                "PlanetClass",
                "Atmosphere",
                "AtmosphereType",
                "AtmosphereComposition",
                "Volcanism",
                "MassEM",
                "SurfaceGravity",
                "SurfacePressure",
                "Landable",
                "Materials",
                "Composition",
                "ReserveLevel",
                "TerraformState",
                "WasDiscovered",
                "WasMapped",
            }
        ),
        "ScanOrganic": frozenset(
            {
                "ScanType",
                "Genus",
                "Genus_Localised",
                "Species",
                "Species_Localised",
                "Variant",
                "Variant_Localised",
                "SystemAddress",
                "Body",
                "BodyID",
                "BodyName",
            }
        ),
        "Screenshot": frozenset(
            {"Filename", "Width", "Height", "System", "SystemAddress", "Body", "BodyID", "Latitude", "Longitude", "Altitude", "Heading"}
        ),
        "SellExplorationData": frozenset({"Systems", "Discovered", "BaseValue", "Bonus"}),
        "SellOrganicData": frozenset({"MarketID", "BioData"}),
        "Touchdown": frozenset(
            {
                "StarSystem",
                "SystemAddress",
                "Body",
                "BodyID",
                "BodyName",
                "Latitude",
                "Longitude",
                "PlayerControlled",
                "NearestDestination",
                "NearestDestination_Localised",
            }
        ),
    }
    EVENT_PAYLOAD_ALLOWLIST: dict[str, frozenset[str]] = {
        event_type: fields | frozenset({"GameVersion", "GameBuild"})
        for event_type, fields in _EVENT_PAYLOAD_FIELDS.items()
    }

    _CONTENT_ADDRESSED = frozenset(
        {
            "Fileheader",
            "LoadGame",
            "Commander",
            "Died",
            "Resurrect",
            "SellExplorationData",
            "MultiSellExplorationData",
            "FSDTarget",
            "NavRoute",
            "NavRouteClear",
        }
    )
    _TRAVEL_EVENTS = frozenset({"FSDJump", "CarrierJump"})
    _BODY_IDENTITY_EVENTS = frozenset(
        {
            "Scan",
            "FSSBodySignals",
            "SAASignalsFound",
            "SAAScanComplete",
            "ApproachBody",
            "LeaveBody",
            "Disembark",
            "Embark",
        }
    )
    _LAT_LON_EVENTS = frozenset({"Touchdown", "Liftoff", "Location"})

    def _reference_strip_payload(
        event_type: str, payload: dict
    ) -> tuple[dict, int]:
        if event_type not in JOURNAL_EVENT_ALLOWLIST:
            raise ValueError(f"unknown journal event type: {event_type!r}")
        allowed = EVENT_PAYLOAD_ALLOWLIST[event_type]
        stripped = {key: value for key, value in payload.items() if key in allowed}
        return stripped, len(payload) - len(stripped)

    def _decimal_str(value: object, *, allow_zero: bool = False) -> str:
        if isinstance(value, bool):
            raise ValueError("boolean is not a journal id")
        if isinstance(value, int):
            number = value
        elif isinstance(value, str) and value.strip().lstrip("-").isdigit():
            number = int(value.strip())
        else:
            raise ValueError(f"not a journal id: {value!r}")
        if number < 0 or (not allow_zero and number == 0):
            raise ValueError(f"out-of-range journal id: {number}")
        return str(number)

    def _required(event_type: str, payload: dict, field: str) -> object:
        if field not in payload or payload[field] is None:
            raise ValueError(f"{event_type} missing required key field {field!r}")
        return payload[field]

    def _canonical_value(value: object) -> object:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return f"{value:.4f}"
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return [_canonical_value(item) for item in value]
        if isinstance(value, dict):
            return {key: _canonical_value(item) for key, item in sorted(value.items())}
        return value

    def _iso_timestamp(event_timestamp: object) -> str:
        if isinstance(event_timestamp, str):
            return event_timestamp.strip()
        return event_timestamp.isoformat()

    def _add_lat_lon(key: dict, payload: dict) -> None:
        if "Latitude" in payload and "Longitude" in payload:
            key["Latitude"] = _canonical_value(payload["Latitude"])
            key["Longitude"] = _canonical_value(payload["Longitude"])

    def _reference_event_identity(
        event_type: str,
        event_payload: dict,
        source_record_hash: bytes,
        *,
        event_timestamp: object | None = None,
    ) -> dict:
        if event_type not in JOURNAL_EVENT_ALLOWLIST:
            raise ValueError(f"unknown journal event type: {event_type!r}")
        if event_type in _CONTENT_ADDRESSED:
            return {"source_record_hash": source_record_hash.hex()}
        if event_type in _TRAVEL_EVENTS:
            if event_timestamp is None:
                raise ValueError(
                    f"{event_type} requires event_timestamp (travel-chronology key)"
                )
            system = _decimal_str(_required(event_type, event_payload, "SystemAddress"))
            return {
                "SystemAddress": system,
                "EventTimestamp": _iso_timestamp(event_timestamp),
            }
        if event_type == "SellOrganicData":
            # Keyed by MarketID + content hash only; no SystemAddress in this event.
            return {
                "MarketID": _decimal_str(_required(event_type, event_payload, "MarketID")),
                "BioDataSha256": _reference_bio_data_sha256(
                    _required(event_type, event_payload, "BioData")
                ).hex(),
            }
        system = _decimal_str(_required(event_type, event_payload, "SystemAddress"))
        if event_type == "CodexEntry":
            key = {
                "SystemAddress": system,
                "BodyID": _decimal_str(
                    _required(event_type, event_payload, "BodyID"), allow_zero=True
                ),
                "EntryID": str(_required(event_type, event_payload, "EntryID")),
            }
            _add_lat_lon(key, event_payload)
            return key
        if event_type == "ScanOrganic":
            body = event_payload.get("BodyID", event_payload.get("Body"))
            if body is None:
                raise ValueError("ScanOrganic missing required key field 'Body'")
            key = {
                "SystemAddress": system,
                "BodyID": _decimal_str(body, allow_zero=True),
                "Genus": str(_required(event_type, event_payload, "Genus")),
                "Species": str(_required(event_type, event_payload, "Species")),
                "ScanType": str(_required(event_type, event_payload, "ScanType")),
            }
            variant = event_payload.get("Variant")
            if variant is not None:
                key["Variant"] = str(variant)
            return key
        if event_type in _BODY_IDENTITY_EVENTS:
            return {
                "SystemAddress": system,
                "BodyID": _decimal_str(
                    _required(event_type, event_payload, "BodyID"), allow_zero=True
                ),
            }
        if event_type in _LAT_LON_EVENTS:
            key = {
                "SystemAddress": system,
                "BodyID": _decimal_str(
                    _required(event_type, event_payload, "BodyID"), allow_zero=True
                ),
            }
            _add_lat_lon(key, event_payload)
            return key
        if event_type == "Screenshot":
            key = {"SystemAddress": system}
            if "BodyID" in event_payload and event_payload["BodyID"] is not None:
                key["BodyID"] = _decimal_str(event_payload["BodyID"], allow_zero=True)
            key["Filename"] = str(_required(event_type, event_payload, "Filename"))
            return key
        if event_type == "Docked":
            return {
                "SystemAddress": system,
                "StationName": str(_required(event_type, event_payload, "StationName")),
            }
        if event_type in {"FSSDiscoveryScan", "FSSAllBodiesFound"}:
            return {"SystemAddress": system}
        raise ValueError(f"no identity rule for event type {event_type!r}")

    def _reference_bio_data_sha256(bio_data: list[dict]) -> bytes:
        canonical = json.dumps(
            _canonical_value(bio_data), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).digest()

    strip_payload = _reference_strip_payload
    event_identity = _reference_event_identity


# ---------------------------------------------------------------------------
# Client-line-discipline reader (mirrors journalParser.ts streamLines +
# parseJournalFilesStreaming for the non-powerplay path).
# ---------------------------------------------------------------------------


@dataclass
class ReaderResult:
    observations: list[dict] = field(default_factory=list)
    skipped_lines: int = 0
    malformed_lines: int = 0
    blank_lines: int = 0


def read_fixture(path: Path) -> ReaderResult:
    """Parse a JSONL fixture with the client worker's line discipline."""
    text = path.read_text(encoding="utf-8")
    result = ReaderResult()
    seen_hashes: set[str] = set()
    # Mirror the worker's streamLines/parseFinalLine: a file ending with a
    # newline has no trailing empty line; a final segment without a newline is
    # still a line. Internal blank lines remain (silently skipped).
    segments = text.split("\n")
    while segments and segments[-1] == "":
        segments.pop()
    for raw_line in segments:
        trimmed = raw_line.rstrip("\r").strip()
        if not trimmed:
            result.blank_lines += 1
            continue
        try:
            record = json.loads(trimmed)
        except json.JSONDecodeError:
            result.malformed_lines += 1
            result.skipped_lines += 1
            continue
        if not isinstance(record, dict) or not isinstance(record.get("event"), str):
            result.malformed_lines += 1
            result.skipped_lines += 1
            continue
        if record["event"] not in JOURNAL_EVENT_ALLOWLIST:
            result.skipped_lines += 1
            continue
        line_hash = hashlib.sha256(trimmed.encode("utf-8")).hexdigest()
        if line_hash in seen_hashes:
            result.skipped_lines += 1
            continue
        seen_hashes.add(line_hash)
        result.observations.append(
            {
                "line_hash": line_hash,
                "event_type": record["event"],
                "payload": record,
                "timestamp": record.get("timestamp"),
            }
        )
    return result


def identity_for(observation: dict) -> tuple[dict, int, dict]:
    """Server-side handling of one parsed line: strip then identity.

    The client strips ``event``/``timestamp`` and allowlist fields before the
    network, so the server-side strip receives the client-shaped payload
    (defense-in-depth re-strip of the same fields).
    """
    client_payload = {
        key: value
        for key, value in observation["payload"].items()
        if key not in ("event", "timestamp")
    }
    stripped, removed = strip_payload(observation["event_type"], client_payload)
    key = event_identity(
        observation["event_type"],
        stripped,
        bytes.fromhex(observation["line_hash"]),
        event_timestamp=observation["timestamp"],
    )
    return stripped, removed, key


def identity_set(observations: list[dict]) -> set[tuple[str, str]]:
    """Distinct (event_type, canonical event_key JSON) identities for a run."""
    return {
        (obs["event_type"], json.dumps(identity_for(obs)[2], sort_keys=True))
        for obs in observations
    }


def fixture_counts(observations: list[dict]) -> Counter:
    return Counter(obs["event_type"] for obs in observations)


# ---------------------------------------------------------------------------
# Contract-level behaviour (documented V3.0 interface invariants).
# ---------------------------------------------------------------------------


def test_contract_implementation_is_available() -> None:
    assert callable(strip_payload)
    assert callable(event_identity)
    assert len(JOURNAL_EVENT_ALLOWLIST) == 30
    assert CONTRACT_IMPL  # recorded; exact string reported in the task report


def test_strip_payload_raises_on_unknown_event_type() -> None:
    with pytest.raises(ValueError):
        strip_payload("TotallyFakeEvent", {"SystemAddress": 1})
    with pytest.raises(ValueError):
        strip_payload("Materials", {"Raw": []})


def test_strip_payload_removes_non_allowlisted_fields() -> None:
    stripped, removed = strip_payload(
        "Scan", {"BodyName": "A", "SystemAddress": 1, "Secret": 42}
    )
    assert removed == 1
    assert "Secret" not in stripped
    assert stripped["BodyName"] == "A"
    assert stripped["SystemAddress"] == 1


def test_sell_organic_data_total_value_is_stripped() -> None:
    # The derived-field trap: TotalValue does not exist in the journal event;
    # a client that ever sent it must have it stripped server-side.
    stripped, removed = strip_payload(
        "SellOrganicData", {"MarketID": 128733992, "BioData": [], "TotalValue": 99999999}
    )
    assert removed == 1
    assert "TotalValue" not in stripped
    assert stripped["MarketID"] == 128733992


def test_fsdjump_same_system_different_timestamp_distinct() -> None:
    payload = {"SystemAddress": 11667293823}
    src = b"ab" * 32
    a = event_identity("FSDJump", payload, src, event_timestamp="2026-07-12T09:01:00Z")
    b = event_identity("FSDJump", payload, src, event_timestamp="2026-07-13T09:01:00Z")
    assert a != b
    assert a["SystemAddress"] == "11667293823"
    assert "EventTimestamp" in a
    with pytest.raises(ValueError):
        event_identity("FSDJump", payload, src)


def test_codexentry_timestamp_not_in_key() -> None:
    base = {"SystemAddress": 4989838266318, "BodyID": 4, "EntryID": "1850573"}
    a = event_identity("CodexEntry", base, b"ab" * 32, event_timestamp="2026-07-12T10:02:10Z")
    b = event_identity("CodexEntry", base, b"cd" * 32, event_timestamp="2026-07-12T10:02:25Z")
    assert a == b


def test_scanorganic_body_renamed() -> None:
    key = event_identity(
        "ScanOrganic",
        {
            "SystemAddress": 4989838266318,
            "Body": 4,
            "Genus": "$Codex_Ent_Genus_Stratum;",
            "Species": "$Codex_Ent_Stratum_07_Name;",
            "Variant": "$Codex_Ent_Stratum_07_F;",
            "ScanType": "Log",
        },
        b"ab" * 32,
    )
    assert key["BodyID"] == "4"
    assert "Body" not in key
    sample = event_identity(
        "ScanOrganic",
        {
            "SystemAddress": 4989838266318,
            "Body": 4,
            "Genus": "$Codex_Ent_Genus_Stratum;",
            "Species": "$Codex_Ent_Stratum_07_Name;",
            "Variant": "$Codex_Ent_Stratum_07_F;",
            "ScanType": "Sample",
        },
        b"ab" * 32,
    )
    assert sample != key
    assert sample["ScanType"] == "Sample"


# ---------------------------------------------------------------------------
# Fixture-level assertions.
# ---------------------------------------------------------------------------


def test_basic_journal_counts() -> None:
    result = read_fixture(FIXTURES_DIR / "basic_journal.jsonl")
    assert result.skipped_lines == 0
    assert result.malformed_lines == 0
    assert result.blank_lines == 0
    assert len(result.observations) == 49
    assert fixture_counts(result.observations) == Counter(
        {
            "Fileheader": 1,
            "LoadGame": 1,
            "FSDJump": 3,
            "Location": 3,
            "FSSDiscoveryScan": 3,
            "FSSAllBodiesFound": 3,
            "Scan": 8,
            "FSSBodySignals": 5,
            "SAASignalsFound": 3,
            "SAAScanComplete": 1,
            "ApproachBody": 3,
            "Touchdown": 3,
            "Disembark": 3,
            "Embark": 3,
            "Liftoff": 3,
            "LeaveBody": 3,
        }
    )
    identities = identity_set(result.observations)
    assert len(identities) == 49  # no internal duplicates in the fixture
    assert all(event_type in JOURNAL_EVENT_ALLOWLIST for event_type, _ in identities)


def test_basic_journal_strips_realistic_non_allowlisted_fields() -> None:
    result = read_fixture(FIXTURES_DIR / "basic_journal.jsonl")
    total_removed = 0
    for obs in result.observations:
        _, removed, _ = identity_for(obs)
        total_removed += removed
    # FSDJump lines carry Population/SystemSecurity/Body/BodyID/BodyType/Docked;
    # Scan lines carry ScanID — none are in the payload allowlist.
    assert total_removed == 3 * 6 + 8 * 1


def test_codex_exo_counts_and_dedupe() -> None:
    result = read_fixture(FIXTURES_DIR / "codex_exo.jsonl")
    assert result.skipped_lines == 0
    assert result.malformed_lines == 0
    assert len(result.observations) == 17
    counts = fixture_counts(result.observations)
    assert counts["Fileheader"] == 1
    assert counts["LoadGame"] == 1
    assert counts["FSDJump"] == 1
    assert counts["SAASignalsFound"] == 1
    assert counts["CodexEntry"] == 3  # raw lines: one EntryID repeated, one distinct
    assert counts["ScanOrganic"] == 6
    assert counts["SellOrganicData"] == 1

    identities = identity_set(result.observations)
    # The repeated CodexEntry (same EntryID, 15 s apart) collapses to one identity.
    codex_keys = {key for event_type, key in identities if event_type == "CodexEntry"}
    assert len(codex_keys) == 2
    # All three ScanOrganic stages stay distinct; all 6 lines are distinct events.
    organic_keys = {key for event_type, key in identities if event_type == "ScanOrganic"}
    assert len(organic_keys) == 6
    assert len(identities) == 16  # 17 lines - 1 collapsed CodexEntry repeat


def test_codex_exo_scanorganic_stage_and_body_rename() -> None:
    result = read_fixture(FIXTURES_DIR / "codex_exo.jsonl")
    organic = [
        (obs, identity_for(obs)[2])
        for obs in result.observations
        if obs["event_type"] == "ScanOrganic"
    ]
    assert len(organic) == 6
    for obs, key in organic:
        assert "Body" not in key
        assert key["BodyID"] in {"4", "5"}
        assert "ScanType" in key
    stages = {key["ScanType"] for _, key in organic}
    assert stages == {"Log", "Sample", "Analyse"}
    by_stage = {(key["Species"], key["BodyID"], key["ScanType"]) for _, key in organic}
    # Species A on body 4 has all three stages; species A on body 5 has Log only
    # (incomplete); species C (Tussock) on body 4 has Log + Sample.
    assert ("$Codex_Ent_Stratum_07_Name;", "4", "Log") in by_stage
    assert ("$Codex_Ent_Stratum_07_Name;", "4", "Sample") in by_stage
    assert ("$Codex_Ent_Stratum_07_Name;", "4", "Analyse") in by_stage
    assert ("$Codex_Ent_Stratum_07_Name;", "5", "Log") in by_stage
    assert ("$Codex_Ent_Tussocks_01_Name;", "4", "Log") in by_stage
    assert ("$Codex_Ent_Tussocks_01_Name;", "4", "Sample") in by_stage


def test_codex_exo_sell_organic_data_without_total_value() -> None:
    result = read_fixture(FIXTURES_DIR / "codex_exo.jsonl")
    sales = [obs for obs in result.observations if obs["event_type"] == "SellOrganicData"]
    assert len(sales) == 1
    payload = sales[0]["payload"]
    assert "MarketID" in payload
    assert "BioData" in payload
    assert "TotalValue" not in payload  # the derived-field trap: journal has none
    stripped, removed, key = identity_for(sales[0])
    assert removed == 0  # MarketID + BioData are allowlisted; nothing to strip
    assert stripped["MarketID"] == 128733992
    assert "MarketID" in key and key["MarketID"] == "128733992"
    assert "BioDataSha256" in key and len(key["BioDataSha256"]) == 64


def test_messy_journal_skips_gracefully() -> None:
    result = read_fixture(FIXTURES_DIR / "messy_journal.jsonl")
    # 1 truncated JSON line, 1 unknown event, 1 real-but-non-allowlisted event,
    # 1 exact duplicate line: all skipped as warnings; the blank line is silent.
    assert result.malformed_lines == 1
    assert result.skipped_lines == 4
    assert result.blank_lines == 1
    assert len(result.observations) == 3
    assert fixture_counts(result.observations) == Counter(
        {"Fileheader": 1, "FSDJump": 2}
    )
    identities = identity_set(result.observations)
    assert len(identities) == 3
    # The trailing partial line (no trailing newline) IS parsed and admitted —
    # the worker's parseFinalLine behaviour, mirrored by the reader.
    assert any(
        obs["event_type"] == "FSDJump"
        and obs["payload"]["SystemAddress"] == 3104491741666
        for obs in result.observations
    )
    # The duplicate line collapsed: only one FSDJump identity for HIP 7337.
    hip_keys = {
        key
        for event_type, key in identities
        if event_type == "FSDJump" and json.loads(key)["SystemAddress"] == "11667293823"
    }
    assert len(hip_keys) == 1


def test_duplicate_content_pair_file_level_dedupe() -> None:
    a = FIXTURES_DIR / "duplicate_content_a.jsonl"
    b = FIXTURES_DIR / "duplicate_content_b.jsonl"
    a_bytes = a.read_bytes()
    b_bytes = b.read_bytes()
    # Byte-identical content: file-level dedupe must skip B entirely.
    assert a_bytes == b_bytes
    assert hashlib.sha256(a_bytes).hexdigest() == hashlib.sha256(b_bytes).hexdigest()
    result_a = read_fixture(a)
    result_b = read_fixture(b)
    assert len(result_a.observations) == 4
    assert len(result_b.observations) == 4
    identities_a = identity_set(result_a.observations)
    identities_b = identity_set(result_b.observations)
    assert identities_a == identities_b
    # File-level dedupe observable: B admits zero NEW identities.
    assert not (identities_b - identities_a)
    assert fixture_counts(result_a.observations) == Counter(
        {"Fileheader": 1, "LoadGame": 1, "FSDJump": 1, "Scan": 1}
    )


def test_reimport_edited_semantic_dedupe() -> None:
    basic = read_fixture(FIXTURES_DIR / "basic_journal.jsonl")
    reimport = read_fixture(FIXTURES_DIR / "reimport_edited.jsonl")
    assert len(basic.observations) == 49
    assert len(reimport.observations) == 49
    assert fixture_counts(basic.observations) == fixture_counts(reimport.observations)

    identities_basic = identity_set(basic.observations)
    identities_reimport = identity_set(reimport.observations)

    # Stable-identity events collapse: same semantic keys after the +1 day
    # shift. Content-addressed events (Fileheader/LoadGame) are per-file
    # metadata keyed by line hash, so they are not part of the collapse set.
    content_addressed = {
        "Fileheader",
        "LoadGame",
        "Commander",
        "Died",
        "Resurrect",
        "SellExplorationData",
        "MultiSellExplorationData",
        "FSDTarget",
        "NavRoute",
        "NavRouteClear",
    }
    stable_types = set(JOURNAL_EVENT_ALLOWLIST) - {"FSDJump", "CarrierJump"} - content_addressed
    stable_basic = {
        (event_type, key)
        for event_type, key in identities_basic
        if event_type in stable_types
    }
    stable_reimport = {
        (event_type, key)
        for event_type, key in identities_reimport
        if event_type in stable_types
    }
    assert stable_basic == stable_reimport
    # 49 events - 3 FSDJumps (travel exception) - 2 content-addressed
    # (Fileheader/LoadGame) = 44 stable identities that collapse.
    assert len(stable_basic) == 49 - 3 - 2

    # Travel-chronology exception: FSDJump keys differ (timestamps shifted).
    jump_basic = {
        key for event_type, key in identities_basic if event_type == "FSDJump"
    }
    jump_reimport = {
        key for event_type, key in identities_reimport if event_type == "FSDJump"
    }
    assert len(jump_basic) == 3
    assert len(jump_reimport) == 3
    assert not (jump_basic & jump_reimport)

    # Content-addressed events (Fileheader/LoadGame) are per-file metadata: the
    # edited file has different line hashes, so their keys differ too.
    addressed_basic = {
        key
        for event_type, key in identities_basic
        if event_type in {"Fileheader", "LoadGame"}
    }
    addressed_reimport = {
        key
        for event_type, key in identities_reimport
        if event_type in {"Fileheader", "LoadGame"}
    }
    assert len(addressed_basic) == 2
    assert len(addressed_reimport) == 2
    assert not (addressed_basic & addressed_reimport)

    # The +1 day shift is real, not cosmetic: spot-check first line timestamps.
    def first_timestamp(observations: list[dict]) -> str:
        return str(observations[0]["timestamp"])

    assert first_timestamp(reimport.observations) == "2026-07-13T09:00:00Z"
    assert first_timestamp(basic.observations) == "2026-07-12T09:00:00Z"


def test_multi_version_variant_presence_changes_identity() -> None:
    result = read_fixture(FIXTURES_DIR / "multi_version.jsonl")
    assert result.skipped_lines == 0
    assert len(result.observations) == 6
    identities = identity_set(result.observations)
    assert len(identities) == 6
    assert fixture_counts(result.observations) == Counter(
        {"Fileheader": 2, "LoadGame": 1, "FSDJump": 1, "ScanOrganic": 2}
    )
    # Both Fileheaders are distinct per-file metadata (content-addressed).
    header_keys = {key for event_type, key in identities if event_type == "Fileheader"}
    assert len(header_keys) == 2

    organics = [
        identity_for(obs)[2]
        for obs in result.observations
        if obs["event_type"] == "ScanOrganic"
    ]
    assert len(organics) == 2
    pre_u15, post_u15 = organics
    # CONFIRMED_RULE C4: pre-U15 ScanOrganic has no Variant -> key shape differs.
    assert pre_u15 == {
        "SystemAddress": "84469133530",
        "BodyID": "2",
        "Genus": "$Codex_Ent_Genus_Tussock;",
        "Species": "$Codex_Ent_Tussocks_01_Name;",
        "ScanType": "Log",
    }
    assert "Body" not in pre_u15
    assert post_u15["Variant"] == "$Codex_Ent_Tussocks_01_A;"
    assert post_u15 != pre_u15


def test_every_fixture_parses_without_raising() -> None:
    """Corpus invariant: no fixture may break the parse -> strip -> identity path."""
    for fixture in sorted(FIXTURES_DIR.glob("*.jsonl")):
        result = read_fixture(fixture)
        for obs in result.observations:
            stripped, removed, key = identity_for(obs)  # must not raise
            assert isinstance(key, dict)
            assert set(stripped) <= EVENT_PAYLOAD_ALLOWLIST[obs["event_type"]]
            assert removed >= 0


# ---------------------------------------------------------------------------
# Generator determinism.
# ---------------------------------------------------------------------------


def test_generator_is_deterministic() -> None:
    from tests.fixtures.journal_v3 import generate_large_journal

    first = generate_large_journal.generate_lines(5_000, seed=20260828)
    second = generate_large_journal.generate_lines(5_000, seed=20260828)
    assert first == second
    assert len(first) == 5_000
    other_seed = generate_large_journal.generate_lines(5_000, seed=20260829)
    assert first != other_seed


def test_generator_lines_are_valid_allowlisted_journal() -> None:
    from tests.fixtures.journal_v3 import generate_large_journal

    lines = generate_large_journal.generate_lines(2_000, seed=20260828)
    observations: list[dict] = []
    for line in lines:
        record = json.loads(line)
        assert isinstance(record, dict)
        assert record["event"] in JOURNAL_EVENT_ALLOWLIST
        observations.append(record)
    assert len(observations) == 2_000
    counts = Counter(record["event"] for record in observations)
    # 2 header lines, then cycles of 12 with 3 ScanOrganic stages each; the
    # partial trailing cycle contributes none.
    assert counts["ScanOrganic"] == 3 * (len(observations) // 12)
    assert counts["Fileheader"] == 1
    assert counts["LoadGame"] == 1
