#!/usr/bin/env python3
"""R1 canonical body evidence foundation.

This module builds versioned, traceable body-evidence aggregates from raw
`systems`, `bodies`, `body_rings`, and `body_scan_facts` only.

It does not compute:
- economy scores
- recommendations
- archetype rankings
- percentiles
- confidence
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


CONTRACT_VERSION = 'canonical_body_semantics_r1/v1'
DRY_RUN_SCHEMA_VERSION = 'r1_canonical_body_evidence_dry_run/v1'
TOOL_NAME = 'r1_canonical_body_evidence'
TOOL_VERSION = 'v1'

CORE_R1_SELECT_SQL = """
WITH target_systems AS (
    SELECT UNNEST(%s::bigint[]) AS system_id64
),
ring_counts AS (
    SELECT body_id, COUNT(*)::integer AS ring_row_count
    FROM body_rings
    GROUP BY body_id
)
SELECT
    s.id64 AS system_id64,
    s.name AS system_name,
    b.id AS body_id,
    b.name AS body_name,
    b.body_type,
    b.subtype,
    b.is_earth_like,
    b.is_water_world,
    b.is_ammonia_world,
    b.is_landable,
    b.is_terraformable,
    b.terraforming_state,
    b.distance_from_star,
    b.bio_signal_count,
    b.geo_signal_count,
    b.atmosphere_type,
    b.atmosphere_composition,
    COALESCE(rc.ring_row_count, 0) AS ring_row_count,
    sf.is_ringed AS scan_is_ringed,
    sf.data_sources AS scan_data_sources
FROM target_systems t
JOIN systems s ON s.id64 = t.system_id64
JOIN bodies b ON b.system_id64 = s.id64
LEFT JOIN ring_counts rc ON rc.body_id = b.id
LEFT JOIN LATERAL (
    SELECT is_ringed, data_sources
    FROM body_scan_facts
    WHERE system_address = b.system_id64
      AND (body_id::bigint = b.id OR body_name = b.name)
    ORDER BY CASE WHEN body_id::bigint = b.id THEN 0 ELSE 1 END, updated_at DESC NULLS LAST
    LIMIT 1
) sf ON TRUE
ORDER BY s.id64, b.id
""".strip()

TRUE_ELW_SUBTYPES = {'earth-like world'}
TRUE_WW_SUBTYPES = {'water world'}
TRUE_AMMONIA_SUBTYPES = {'ammonia world'}
GG_AMMONIA_LIFE_SUBTYPES = {
    'gas giant with ammonia-based life',
    'gas giant with ammonia based life',
}
GG_WATER_LIFE_SUBTYPES = {
    'gas giant with water-based life',
    'gas giant with water based life',
}
BLACK_HOLE_SUBTYPES = {'black hole'}
NEUTRON_STAR_SUBTYPES = {'neutron star'}
WHITE_DWARF_SUBTYPES = {
    'white dwarf (d)',
    'white dwarf (da)',
    'white dwarf (dab)',
    'white dwarf (daz)',
    'white dwarf (db)',
    'white dwarf (dbz)',
    'white dwarf (dc)',
    'white dwarf (dq)',
    'white dwarf (dx)',
    'd (white dwarf) star',
    'da (white dwarf) star',
    'dab (white dwarf) star',
    'daz (white dwarf) star',
    'db (white dwarf) star',
    'dbz (white dwarf) star',
    'dc (white dwarf) star',
    'dq (white dwarf) star',
    'dx (white dwarf) star',
}
GAS_GIANT_SUBTYPES = {
    'gas giant',
    'class i gas giant',
    'class ii gas giant',
    'class iii gas giant',
    'class iv gas giant',
    'class v gas giant',
    'helium-rich gas giant',
    *GG_AMMONIA_LIFE_SUBTYPES,
    *GG_WATER_LIFE_SUBTYPES,
}
ROCKY_SUBTYPES = {'rocky body'}
ROCKY_ICE_SUBTYPES = {'rocky ice body'}
ICY_SUBTYPES = {'icy body'}
HMC_SUBTYPES = {'high metal content body'}
METAL_RICH_SUBTYPES = {'metal-rich body'}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def artifact_sha256(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop('artifact_integrity', None)
    return hashlib.sha256(canonical_json(payload).encode('utf-8')).hexdigest()


def normalise_text(value: Any) -> str | None:
    if value is None:
        return None
    text = ' '.join(str(value).strip().split())
    return text.casefold() if text else None


def optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {'true', 't', '1', 'yes'}:
            return True
        if lowered in {'false', 'f', '0', 'no'}:
            return False
    return None


@dataclass(frozen=True)
class BodyClassification:
    system_id64: int
    body_id: int
    body_name: str
    canonical_facts: dict[str, Any]
    raw_evidence: dict[str, Any]
    applied_rule_ids: list[str]
    unknown_flags: list[str]
    ambiguous_flags: list[str]
    completeness_state: str

    def as_dict(self) -> dict[str, Any]:
        return {
            'system_id64': self.system_id64,
            'body_id': self.body_id,
            'body_name': self.body_name,
            'canonical_facts': self.canonical_facts,
            'raw_evidence': self.raw_evidence,
            'applied_rule_ids': self.applied_rule_ids,
            'unknown_flags': self.unknown_flags,
            'ambiguous_flags': self.ambiguous_flags,
            'completeness_state': self.completeness_state,
        }


def _identity_or_exact_bool(
    subtype: str | None,
    explicit_value: Any,
    exact_subtypes: set[str],
    explicit_rule: str,
    subtype_rule: str,
    unknown_flag: str,
    applied: list[str],
    unknowns: list[str],
) -> bool | None:
    explicit = optional_bool(explicit_value)
    if explicit is True:
        applied.append(explicit_rule)
        return True
    if subtype in exact_subtypes:
        applied.append(subtype_rule)
        return True
    if subtype is None and explicit is None:
        unknowns.append(unknown_flag)
        return None
    return False


def _exact_subtype(
    subtype: str | None,
    exact_subtypes: set[str],
    rule_id: str,
    unknown_flag: str,
    applied: list[str],
    unknowns: list[str],
) -> bool | None:
    if subtype is None:
        unknowns.append(unknown_flag)
        return None
    if subtype in exact_subtypes:
        applied.append(rule_id)
        return True
    return False


def _distance_band(value: float | None) -> str:
    if value is None:
        return 'unknown'
    if value <= 1000:
        return '0_1k_ls'
    if value <= 10000:
        return '1k_10k_ls'
    if value <= 50000:
        return '10k_50k_ls'
    if value <= 100000:
        return '50k_100k_ls'
    return '100k_plus_ls'


def classify_body_row(row: Mapping[str, Any]) -> BodyClassification:
    subtype = normalise_text(row.get('subtype'))
    applied: list[str] = []
    unknowns: list[str] = []
    ambiguous: list[str] = []

    true_earth_like_world = _identity_or_exact_bool(
        subtype, row.get('is_earth_like'), TRUE_ELW_SUBTYPES,
        'R1.BODY.IDENTITY.TRUE_ELW.EXPLICIT_BOOL',
        'R1.BODY.IDENTITY.TRUE_ELW.EXACT_SUBTYPE',
        'missing_special_body_boolean',
        applied, unknowns,
    )
    true_water_world = _identity_or_exact_bool(
        subtype, row.get('is_water_world'), TRUE_WW_SUBTYPES,
        'R1.BODY.IDENTITY.TRUE_WW.EXPLICIT_BOOL',
        'R1.BODY.IDENTITY.TRUE_WW.EXACT_SUBTYPE',
        'missing_special_body_boolean',
        applied, unknowns,
    )
    true_ammonia_world = _identity_or_exact_bool(
        subtype, row.get('is_ammonia_world'), TRUE_AMMONIA_SUBTYPES,
        'R1.BODY.IDENTITY.TRUE_AMMONIA_WORLD.EXPLICIT_BOOL',
        'R1.BODY.IDENTITY.TRUE_AMMONIA_WORLD.EXACT_SUBTYPE',
        'missing_special_body_boolean',
        applied, unknowns,
    )

    gas_giant_ammonia_life = _exact_subtype(
        subtype, GG_AMMONIA_LIFE_SUBTYPES,
        'R1.BODY.LIFE.GAS_GIANT_AMMONIA_BASED_LIFE.EXACT_SUBTYPE',
        'missing_subtype', applied, unknowns,
    )
    gas_giant_water_life = _exact_subtype(
        subtype, GG_WATER_LIFE_SUBTYPES,
        'R1.BODY.LIFE.GAS_GIANT_WATER_BASED_LIFE.EXACT_SUBTYPE',
        'missing_subtype', applied, unknowns,
    )
    black_hole = _exact_subtype(subtype, BLACK_HOLE_SUBTYPES, 'R1.BODY.IDENTITY.BLACK_HOLE.EXACT_SUBTYPE', 'missing_subtype', applied, unknowns)
    neutron_star = _exact_subtype(subtype, NEUTRON_STAR_SUBTYPES, 'R1.BODY.IDENTITY.NEUTRON_STAR.EXACT_SUBTYPE', 'missing_subtype', applied, unknowns)
    white_dwarf = _exact_subtype(subtype, WHITE_DWARF_SUBTYPES, 'R1.BODY.IDENTITY.WHITE_DWARF.EXACT_SUBTYPE', 'missing_subtype', applied, unknowns)
    gas_giant = _exact_subtype(subtype, GAS_GIANT_SUBTYPES, 'R1.BODY.IDENTITY.GAS_GIANT.EXACT_SUBTYPE', 'missing_subtype', applied, unknowns)
    rocky = _exact_subtype(subtype, ROCKY_SUBTYPES, 'R1.BODY.IDENTITY.ROCKY.EXACT_SUBTYPE', 'missing_subtype', applied, unknowns)
    rocky_ice = _exact_subtype(subtype, ROCKY_ICE_SUBTYPES, 'R1.BODY.IDENTITY.ROCKY_ICE.EXACT_SUBTYPE', 'missing_subtype', applied, unknowns)
    icy = _exact_subtype(subtype, ICY_SUBTYPES, 'R1.BODY.IDENTITY.ICY.EXACT_SUBTYPE', 'missing_subtype', applied, unknowns)
    high_metal_content = _exact_subtype(subtype, HMC_SUBTYPES, 'R1.BODY.IDENTITY.HIGH_METAL_CONTENT.EXACT_SUBTYPE', 'missing_subtype', applied, unknowns)
    metal_rich = _exact_subtype(subtype, METAL_RICH_SUBTYPES, 'R1.BODY.IDENTITY.METAL_RICH.EXACT_SUBTYPE', 'missing_subtype', applied, unknowns)

    landable = optional_bool(row.get('is_landable'))
    if landable is None:
        unknowns.append('missing_landable_flag')
    else:
        applied.append('R1.BODY.STATE.LANDABLE.RAW_BOOL')

    terraformable_bool = optional_bool(row.get('is_terraformable'))
    terraform_state = normalise_text(row.get('terraforming_state'))
    if terraformable_bool is True:
        terraformable = True
        applied.append('R1.BODY.STATE.TERRAFORMABLE.RAW_BOOL')
    elif terraform_state in {'terraformable', 'terraformed'}:
        terraformable = True
        applied.append('R1.BODY.STATE.TERRAFORMABLE.RAW_STATE')
    elif terraformable_bool is False or terraform_state is not None:
        terraformable = False
    else:
        terraformable = None
        unknowns.append('missing_terraformable_state')

    ring_row_count = int(row.get('ring_row_count') or 0)
    scan_is_ringed = optional_bool(row.get('scan_is_ringed'))
    scan_sources = [normalise_text(x) for x in (row.get('scan_data_sources') or []) if normalise_text(x)]
    if ring_row_count > 0:
        rings = True
        applied.append('R1.BODY.RINGS.BODY_RINGS_PRESENT')
        ring_source_status = 'body_rings'
    elif scan_is_ringed is True:
        rings = True
        applied.append('R1.BODY.RINGS.SCAN_FLAG_TRUE')
        ring_source_status = 'body_scan_facts'
    elif scan_is_ringed is False and 'eddn_scan' in scan_sources:
        rings = False
        applied.append('R1.BODY.RINGS.SCAN_FLAG_FALSE')
        ring_source_status = 'body_scan_facts'
    else:
        rings = None
        ring_source_status = 'unknown'
        unknowns.append('unknown_ring_state')

    bio_raw = row.get('bio_signal_count')
    if bio_raw is None:
        biological_signals = None
        unknowns.append('missing_bio_signal_count')
    else:
        biological_signals = int(bio_raw) > 0
        applied.append('R1.BODY.SIGNALS.BIO_COUNT')

    geo_raw = row.get('geo_signal_count')
    if geo_raw is None:
        geological_signals = None
        unknowns.append('missing_geo_signal_count')
    else:
        geological_signals = int(geo_raw) > 0
        applied.append('R1.BODY.SIGNALS.GEO_COUNT')

    distance_raw = row.get('distance_from_star')
    distance = float(distance_raw) if distance_raw is not None else None
    if distance is None:
        unknowns.append('missing_distance_from_arrival_star')
        distance_source_status = 'unknown'
    else:
        applied.append('R1.BODY.DISTANCE.FROM_ARRIVAL_STAR.PRESENT')
        distance_source_status = 'raw_body_distance'

    canonical_facts = {
        'true_earth_like_world': true_earth_like_world,
        'true_water_world': true_water_world,
        'true_ammonia_world': true_ammonia_world,
        'gas_giant_ammonia_life': gas_giant_ammonia_life,
        'gas_giant_water_life': gas_giant_water_life,
        'black_hole': black_hole,
        'neutron_star': neutron_star,
        'white_dwarf': white_dwarf,
        'gas_giant': gas_giant,
        'rocky': rocky,
        'rocky_ice': rocky_ice,
        'icy': icy,
        'high_metal_content': high_metal_content,
        'metal_rich': metal_rich,
        'landable': landable,
        'terraformable': terraformable,
        'rings': rings,
        'biological_signals': biological_signals,
        'geological_signals': geological_signals,
        'distance_from_arrival_star_ls': distance,
        'distance_band': _distance_band(distance),
        'distance_source_status': distance_source_status,
        'ring_source_status': ring_source_status,
    }
    raw_evidence = {
        'raw_subtype': row.get('subtype'),
        'normalised_subtype': subtype,
        'raw_is_earth_like': row.get('is_earth_like'),
        'raw_is_water_world': row.get('is_water_world'),
        'raw_is_ammonia_world': row.get('is_ammonia_world'),
        'raw_is_landable': row.get('is_landable'),
        'raw_is_terraformable': row.get('is_terraformable'),
        'raw_terraforming_state': row.get('terraforming_state'),
        'raw_distance_from_star': row.get('distance_from_star'),
        'raw_bio_signal_count': row.get('bio_signal_count'),
        'raw_geo_signal_count': row.get('geo_signal_count'),
        'raw_atmosphere_type': row.get('atmosphere_type'),
        'raw_atmosphere_composition': row.get('atmosphere_composition'),
        'raw_ring_row_count': row.get('ring_row_count'),
        'raw_scan_is_ringed': row.get('scan_is_ringed'),
        'raw_scan_data_sources': row.get('scan_data_sources'),
    }
    return BodyClassification(
        system_id64=int(row['system_id64']),
        body_id=int(row['body_id']),
        body_name=str(row['body_name']),
        canonical_facts=canonical_facts,
        raw_evidence=raw_evidence,
        applied_rule_ids=sorted(set(applied)),
        unknown_flags=sorted(set(unknowns)),
        ambiguous_flags=sorted(set(ambiguous)),
        completeness_state='complete' if not unknowns else 'partial',
    )


def aggregate_system_classifications(system_id64: int, system_name: str | None, body_rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    traces = [
        classify_body_row({'system_id64': system_id64, 'system_name': system_name, **dict(row)}).as_dict()
        for row in body_rows
    ]
    known_distances = [t['canonical_facts']['distance_from_arrival_star_ls'] for t in traces if t['canonical_facts']['distance_from_arrival_star_ls'] is not None]
    aggregate = {
        'system_id64': int(system_id64),
        'system_name': system_name,
        'total_body_rows_seen': len(body_rows),
        'total_body_rows_classified': len(traces),
        'unknown_body_count': sum(1 for t in traces if t['unknown_flags']),
        'true_earth_like_world_count': sum(t['canonical_facts']['true_earth_like_world'] is True for t in traces),
        'true_water_world_count': sum(t['canonical_facts']['true_water_world'] is True for t in traces),
        'true_ammonia_world_count': sum(t['canonical_facts']['true_ammonia_world'] is True for t in traces),
        'gas_giant_ammonia_life_count': sum(t['canonical_facts']['gas_giant_ammonia_life'] is True for t in traces),
        'gas_giant_water_life_count': sum(t['canonical_facts']['gas_giant_water_life'] is True for t in traces),
        'black_hole_count': sum(t['canonical_facts']['black_hole'] is True for t in traces),
        'neutron_star_count': sum(t['canonical_facts']['neutron_star'] is True for t in traces),
        'white_dwarf_count': sum(t['canonical_facts']['white_dwarf'] is True for t in traces),
        'gas_giant_count': sum(t['canonical_facts']['gas_giant'] is True for t in traces),
        'rocky_count': sum(t['canonical_facts']['rocky'] is True for t in traces),
        'rocky_ice_count': sum(t['canonical_facts']['rocky_ice'] is True for t in traces),
        'icy_count': sum(t['canonical_facts']['icy'] is True for t in traces),
        'high_metal_content_count': sum(t['canonical_facts']['high_metal_content'] is True for t in traces),
        'metal_rich_count': sum(t['canonical_facts']['metal_rich'] is True for t in traces),
        'landable_count': sum(t['canonical_facts']['landable'] is True for t in traces),
        'terraformable_count': sum(t['canonical_facts']['terraformable'] is True for t in traces),
        'ringed_body_count': sum(t['canonical_facts']['rings'] is True for t in traces),
        'biological_signal_body_count': sum(t['canonical_facts']['biological_signals'] is True for t in traces),
        'geological_signal_body_count': sum(t['canonical_facts']['geological_signals'] is True for t in traces),
        'biological_signal_total': sum(int(t['raw_evidence']['raw_bio_signal_count'] or 0) for t in traces),
        'geological_signal_total': sum(int(t['raw_evidence']['raw_geo_signal_count'] or 0) for t in traces),
        'body_data_completeness_state': 'complete' if all(not t['unknown_flags'] for t in traces) else ('unknown' if all(t['unknown_flags'] for t in traces) else 'partial'),
        'min_distance_from_arrival_star_ls': min(known_distances) if known_distances else None,
        'max_distance_from_arrival_star_ls': max(known_distances) if known_distances else None,
        'distance_known_body_count': len(known_distances),
        'distance_unknown_body_count': len(traces) - len(known_distances),
        'identity_fields_complete': all('missing_subtype' not in t['unknown_flags'] and 'missing_special_body_boolean' not in t['unknown_flags'] for t in traces),
        'distance_fields_complete': all('missing_distance_from_arrival_star' not in t['unknown_flags'] for t in traces),
        'ring_fields_complete': all('unknown_ring_state' not in t['unknown_flags'] for t in traces),
        'signal_fields_complete': all('missing_bio_signal_count' not in t['unknown_flags'] and 'missing_geo_signal_count' not in t['unknown_flags'] for t in traces),
        'atmosphere_fields_complete': all(t['raw_evidence']['raw_atmosphere_type'] is not None for t in traces),
    }
    aggregate['earth_like_world_count'] = aggregate['true_earth_like_world_count']
    aggregate['water_world_count'] = aggregate['true_water_world_count']
    aggregate['ammonia_world_count'] = aggregate['true_ammonia_world_count']
    return aggregate, traces


def evaluate_expectations(aggregate: Mapping[str, Any], expectations: Mapping[str, Any]) -> dict[str, Any]:
    checks = []
    passed = True
    for field in sorted(expectations):
        ok = aggregate.get(field) == expectations[field]
        passed = passed and ok
        checks.append({'field': field, 'expected': expectations[field], 'actual': aggregate.get(field), 'pass': ok})
    return {'pass': passed, 'checks': checks}


def build_dry_run_report_from_cases(systems: Sequence[Mapping[str, Any]], *, source_snapshot_identifier: str, generated_at: str | None = None, git_commit: str | None = None) -> dict[str, Any]:
    reports = []
    source_rows = 0
    for system in sorted(systems, key=lambda x: int(x['system_id64'])):
        aggregate, traces = aggregate_system_classifications(int(system['system_id64']), system.get('name'), list(system.get('bodies') or []))
        reports.append({
            'system_id64': int(system['system_id64']),
            'system_name': system.get('name'),
            'legacy_comparison': system.get('legacy_comparison') or {},
            'expected': system.get('expectations') or {},
            'expectation_result': evaluate_expectations(aggregate, system.get('expectations') or {}),
            'aggregate': aggregate,
            'body_classification_trace': traces,
        })
        source_rows += len(system.get('bodies') or [])
    report = {
        'schema_version': DRY_RUN_SCHEMA_VERSION,
        'generated_at': generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        'tool': {'name': TOOL_NAME, 'version': TOOL_VERSION, 'git_commit': git_commit},
        'contract_version': CONTRACT_VERSION,
        'dry_run': True,
        'scope': {
            'mode': 'bounded_fixture_corpus',
            'system_id64_list': [r['system_id64'] for r in reports],
            'system_count': len(reports),
        },
        'source_snapshot_identifier': source_snapshot_identifier,
        'summary': {
            'systems_evaluated': len(reports),
            'source_body_rows': source_rows,
            'systems_passing_expectations': sum(1 for r in reports if r['expectation_result']['pass']),
            'systems_failing_expectations': sum(1 for r in reports if not r['expectation_result']['pass']),
        },
        'query_contract_proof': {
            'core_r1_select_sql': CORE_R1_SELECT_SQL,
            'allowed_core_tables': ['systems', 'bodies', 'body_rings', 'body_scan_facts'],
            'forbidden_inputs_absent': all(
                forbidden not in CORE_R1_SELECT_SQL.casefold()
                for forbidden in ('ratings', 'score_', 'economy_suggestion', 'score_breakdown', 'system_archetype_scores', 'system_archetype_traits', 'mv_archetype_rankings')
            ),
        },
        'systems': reports,
    }
    report['artifact_integrity'] = {'canonical_json_sha256': artifact_sha256(report)}
    return report


def load_fixture_cases(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    return [dict(x) for x in payload['systems']], dict(payload)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build bounded R1 canonical body evidence dry-run report')
    parser.add_argument('--fixture-json', type=Path, required=True)
    parser.add_argument('--output-json', type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    systems, meta = load_fixture_cases(args.fixture_json)
    report = build_dry_run_report_from_cases(
        systems,
        source_snapshot_identifier=meta.get('source_snapshot_identifier') or args.fixture_json.name,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True)
    if args.output_json:
        args.output_json.write_text(rendered + '\n', encoding='utf-8')
    else:
        sys.stdout.write(rendered + '\n')
    return 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
