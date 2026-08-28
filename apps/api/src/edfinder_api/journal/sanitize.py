"""V3 journal sanitization: A1-A14 allowlist mapping (Task 4).

Maps a normalized ``v3_private.journal_event`` row (with its canonical
event key and stripped payload) to a sanitized export observation, or None
for excluded event types. Authority: the A1-A14 sanitization table in the
implementation plan and the V3 journal-intelligence decision doc's
ED-Finder -> CRE boundary (sanitization model). Fail-closed: any field not
listed in the A1-A14 table is never copied into the output.

Hard exclusions enforced here: Latitude/Longitude (default excluded, even
when present in the event key or payload), credits (Value/Bonus/TotalValue),
MarketID, Commander name/FID, and the entire rows of travel/identity events
(return None). The output carries ``observed_week`` (ISO-8601 week bucket)
only — never an exact timestamp. ``body_id`` is the journal body id from the
event key — never ed-finder's ``bodies.id``; this module has no access to
canonical tables at all.

Row contract (dict)::

    {
        "event_type": str,
        "event_key": dict | str(json)      # canonical key, identity.py output
        "event_payload": dict | str(json), # allowlist-stripped payload
        "event_timestamp": datetime,       # tz-aware UTC (naive -> assumed UTC)
        "source_record_hash": bytes | str  # 32-byte hash; hex string accepted
    }

Exported event set (everything else returns None): Scan, FSSBodySignals,
SAASignalsFound, SAAScanComplete, CodexEntry, ScanOrganic, SellOrganicData,
FSSDiscoveryScan, FSSAllBodiesFound. FSSDiscoveryScan/FSSAllBodiesFound are
system-level observations with no body fields (recorded deviation).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

OBSERVATION_NAMESPACE_UUID = UUID('6ba7b811-9dad-11d1-80b4-00c04fd430c8')

EVIDENCE_QUALITY = 'OBSERVED_PERSONAL'

# Event types never exported; sanitize_observation returns None for these.
EXCLUDED_EVENT_TYPES = frozenset({
    'FSDJump', 'CarrierJump', 'Location', 'Touchdown', 'Liftoff', 'ApproachBody',
    'LeaveBody', 'Disembark', 'Embark', 'Screenshot', 'Docked', 'Fileheader',
    'LoadGame', 'Commander', 'Died', 'Resurrect', 'SellExplorationData',
    'MultiSellExplorationData', 'FSDTarget', 'NavRoute', 'NavRouteClear',
})

# The exported set = the 30-event allowlist minus EXCLUDED_EVENT_TYPES.
EXPORTED_EVENT_TYPES = frozenset({
    'Scan', 'FSSBodySignals', 'SAASignalsFound', 'SAAScanComplete',
    'CodexEntry', 'ScanOrganic', 'SellOrganicData', 'FSSDiscoveryScan',
    'FSSAllBodiesFound',
})

# Event types whose payload contributes a normalized body_environment block.
_ENVIRONMENT_EVENT_TYPES = frozenset({'Scan', 'FSSBodySignals', 'SAASignalsFound'})

# Event types whose payload contributes a signals/genuses block.
_SIGNALS_EVENT_TYPES = frozenset({'FSSBodySignals', 'SAASignalsFound'})

# body_environment: normalized key -> journal payload field(s), values
# passed through verbatim (journal strings/floats only — no derivation).
# Units remain journal-native (Radius is meters, SurfaceGravity m/s^2,
# SurfaceTemperature K) — documented in the export contract.
_ENVIRONMENT_FIELD_MAP: dict[str, tuple[str, ...]] = {
    'body_class': ('BodyClass', 'PlanetClass'),
    'star_type': ('StarType',),
    'atmosphere': ('Atmosphere',),
    'volcanism': ('Volcanism',),
    'mass_em': ('MassEM',),
    'radius_km': ('Radius',),
    'surface_gravity_g': ('SurfaceGravity',),
    'surface_temperature_k': ('SurfaceTemperature',),
    'landable': ('Landable',),
    'terraform_state': ('TerraformState',),
}


def minimize_time(dt: datetime) -> str:
    """ISO-8601 week bucket for a timestamp: ``f"{iso_year}-W{iso_week:02d}"``.

    The exact timestamp never leaves this function; consumers get the week
    only. Naive datetimes are assumed UTC (matching the journal identity
    contract). ISO-8601 weeks can belong to a different calendar year at
    the edges (e.g. 2027-01-01 -> "2026-W53").
    """
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        # Naive timestamps are assumed UTC (journal identity contract).
        dt = dt.replace(tzinfo=timezone.utc)
    iso = dt.isocalendar()
    return f'{iso.year}-W{iso.week:02d}'


def _as_dict(value: Any, *, field: str) -> dict:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f'{field} is not valid JSON: {exc}') from exc
        if not isinstance(decoded, dict):
            raise ValueError(f'{field} must decode to a JSON object')
        return decoded
    if not isinstance(value, dict):
        raise ValueError(f'{field} must be a dict or JSON object string')
    return value


def _canonical_key_json(event_key: dict) -> str:
    """Deterministic JSON of the canonical event key (sorted keys, compact
    separators, ascii-escaped) — the uuid5 namespace-string input."""
    return json.dumps(event_key, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def _source_hash_hex(source_record_hash: Any) -> str:
    if isinstance(source_record_hash, (bytes, bytearray)):
        return bytes(source_record_hash).hex()
    if isinstance(source_record_hash, str):
        return source_record_hash.lower()
    raise ValueError(f'source_record_hash must be bytes or hex str, got {type(source_record_hash).__name__}')


def _environment_block(payload: dict) -> dict | None:
    """Normalized body/environment facts from Scan/FSSBodySignals/
    SAASignalsFound payloads; absent keys are omitted (fail-closed)."""
    block: dict[str, Any] = {}
    for normalized_name, journal_names in _ENVIRONMENT_FIELD_MAP.items():
        for journal_name in journal_names:
            if journal_name in payload and payload[journal_name] is not None:
                block[normalized_name] = payload[journal_name]
                break
    return block or None


def _signals_block(event_type: str, payload: dict) -> dict | None:
    """Signals (counts, verbatim entries) and Genuses (projected to canonical
    genus tokens; localised names are not allowlisted) for FSSBodySignals /
    SAASignalsFound. Null values inside entries are dropped — the CRE
    consumer schema rejects JSON nulls, so no null may ever be emitted."""
    block: dict[str, Any] = {}
    if event_type not in _SIGNALS_EVENT_TYPES:
        return None
    if 'Signals' in payload and payload['Signals'] is not None:
        signals = payload['Signals']
        if not isinstance(signals, list):
            raise ValueError('payload Signals must be a list')
        block['signals'] = [
            {k: v for k, v in entry.items() if v is not None}
            for entry in signals
            if isinstance(entry, dict)
        ]
    if 'Genuses' in payload and payload['Genuses'] is not None:
        genuses = payload['Genuses']
        if not isinstance(genuses, list):
            raise ValueError('payload Genuses must be a list')
        block['genuses'] = [
            entry['Genus']
            for entry in genuses
            if isinstance(entry, dict) and entry.get('Genus') is not None
        ]
    return block or None


def _sale_block(payload: dict) -> list[dict] | None:
    """SellOrganicData sale entries: {genus, species, variant, count} only.
    MarketID, Value/Bonus/TotalValue and localised Name are hard-excluded."""
    bio_data = payload.get('BioData')
    if bio_data is None:
        return None
    if not isinstance(bio_data, list):
        raise ValueError('payload BioData must be a list')
    sale: list[dict] = []
    for item in bio_data:
        if not isinstance(item, dict):
            continue
        entry: dict[str, Any] = {}
        for token_key in ('Genus', 'Species', 'Variant'):
            if item.get(token_key) is not None:
                entry[token_key.lower()] = item[token_key]
        if item.get('Count') is not None:
            entry['count'] = item['Count']
        if entry:
            sale.append(entry)
    return sale or None


def sanitize_observation(event_row: dict) -> dict | None:
    """Map a journal_event row to a sanitized export observation (A1-A14).

    Returns None for excluded event types (travel/identity/credit/route
    events). Raises ValueError on structurally invalid rows. The output dict
    contains ONLY the A1-A14 allowlisted fields; hard exclusions (lat/long,
    credits, MarketID, commander identity) can never appear.
    """
    event_type = event_row['event_type']
    if event_type not in EXPORTED_EVENT_TYPES:
        return None

    event_key = _as_dict(event_row['event_key'], field='event_key')
    payload = _as_dict(event_row['event_payload'], field='event_payload')
    event_timestamp = event_row['event_timestamp']

    observation: dict[str, Any] = {
        'observation_id': str(uuid.uuid5(
            OBSERVATION_NAMESPACE_UUID,
            f'{event_type}:{_canonical_key_json(event_key)}',
        )),
        'observation_type': event_type,
        'observed_week': minimize_time(event_timestamp),
        'source_event_sha256': _source_hash_hex(event_row['source_record_hash']),
        'evidence_quality': EVIDENCE_QUALITY,
    }

    # system / body identity from the canonical event key. Canonical keys
    # already carry decimal strings (identity contract); str() is a
    # fail-safe so the export shape is always decimal-string regardless of
    # the input representation. Null values are treated as absent.
    system_id64: str | None = None
    if event_key.get('SystemAddress') is not None:
        system_id64 = str(event_key['SystemAddress'])
    body_id: str | None = None
    if event_key.get('BodyID') is not None:
        body_id = str(event_key['BodyID'])

    # system_name: observed value only (payload, never derived).
    system_name = payload.get('SystemName')
    if system_name is None:
        system_name = payload.get('StarSystem')

    # CRE contract (schema review directive): system_id64 and system_name
    # are ALWAYS present for every exported observation type EXCEPT
    # SellOrganicData, which omits both. A row that cannot satisfy the
    # contract is an integrity anomaly — fail closed rather than emit a
    # schema-invalid observation.
    if event_type != 'SellOrganicData':
        if system_id64 is None:
            raise ValueError(
                f'{event_type} export requires event_key SystemAddress '
                '(contract: system_id64 always present)'
            )
        if system_name is None:
            raise ValueError(
                f'{event_type} export requires a payload system name '
                '(SystemName/StarSystem) (contract: system_name always present)'
            )
        observation['system_id64'] = system_id64
        observation['system_name'] = system_name
    # else: SellOrganicData has no system identity (key = MarketID +
    # BioDataSha256) and deliberately OMITS both system fields.

    if body_id is not None:
        observation['body_id'] = body_id

    # body_name: payload BodyName, else string form of payload Body.
    body_name = payload.get('BodyName')
    if body_name is None and payload.get('Body') is not None:
        body_name = str(payload['Body'])
    if body_name is not None:
        observation['body_name'] = body_name

    # Per-type allowlisted blocks.
    if event_type in _ENVIRONMENT_EVENT_TYPES:
        env = _environment_block(payload)
        if env is not None:
            observation['body_environment'] = env
    if event_type in _SIGNALS_EVENT_TYPES:
        signals = _signals_block(event_type, payload)
        if signals is not None:
            observation.update(signals)
    if event_type == 'CodexEntry':
        if payload.get('Region') is not None:
            observation['codex_region'] = payload['Region']
        if event_key.get('EntryID') is not None:
            observation['codex_entry_id'] = event_key['EntryID']
    if event_type == 'ScanOrganic':
        for token_key in ('Genus', 'Species', 'Variant'):
            if payload.get(token_key) is not None:
                observation[token_key.lower()] = payload[token_key]
    if event_type == 'SellOrganicData':
        sale = _sale_block(payload)
        if sale is not None:
            observation['sale'] = sale

    # Game version/build attach (client V3 parser rolling state).
    if payload.get('GameVersion') is not None:
        observation['game_version'] = payload['GameVersion']
    if payload.get('GameBuild') is not None:
        observation['game_build'] = payload['GameBuild']

    return observation
