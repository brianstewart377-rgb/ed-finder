#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg


ROOT = Path(__file__).resolve().parents[2]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if not API_SRC.is_dir():
    API_SRC = Path('/app')

if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from review_environment_fixtures import (  # noqa: E402
    REVIEW_PROVENANCE_CONTRACTS,
    REVIEW_SYSTEMS,
    REVIEW_WAREHOUSE_CONTRACTS,
    review_provenance_contract_key,
    review_warehouse_contract_key,
)
from review_runtime_guard import (  # noqa: E402
    EXPECTED_REVIEW_DATABASE_NAME,
    validate_review_runtime_env,
)


EXPECTED_REVIEW_DB_NAME = EXPECTED_REVIEW_DATABASE_NAME


class ReviewSeedError(RuntimeError):
    """Raised when a review-only seed operation is unsafe."""


def review_system_names() -> tuple[str, ...]:
    return tuple(system['name'] for system in REVIEW_SYSTEMS)


def assert_review_database_name(database_name: str) -> None:
    if database_name != EXPECTED_REVIEW_DB_NAME:
        raise ReviewSeedError(
            f'review seed refused unsafe database {database_name!r}; expected {EXPECTED_REVIEW_DB_NAME!r}'
        )


async def ensure_review_seed(pool: asyncpg.Pool) -> dict[str, int]:
    async with pool.acquire() as conn:
        database_name = await conn.fetchval('SELECT current_database()')
        assert_review_database_name(str(database_name or ''))
        await _upsert_app_meta(conn)
        await _upsert_systems(conn)
        await _upsert_bodies(conn)
        await _upsert_stations(conn)
        await _upsert_ratings(conn)
        await _upsert_review_contracts(conn)
        row = await conn.fetchrow(
            """
            SELECT
              COUNT(*) FILTER (WHERE name LIKE 'Review %')::int AS systems,
              (SELECT COUNT(*)::int FROM bodies WHERE system_id64 = ANY($1::bigint[])) AS bodies,
              (SELECT COUNT(*)::int FROM stations WHERE system_id64 = ANY($1::bigint[])) AS stations,
              (SELECT COUNT(*)::int FROM ratings WHERE system_id64 = ANY($1::bigint[])) AS ratings
            FROM systems
            WHERE id64 = ANY($1::bigint[])
            """,
            _review_ids(),
        )
    return {
        'systems': int(row['systems']),
        'bodies': int(row['bodies']),
        'stations': int(row['stations']),
        'ratings': int(row['ratings']),
        'warehouse_contracts': len(REVIEW_WAREHOUSE_CONTRACTS),
        'provenance_contracts': len(REVIEW_PROVENANCE_CONTRACTS),
    }


def _review_ids() -> list[int]:
    return [int(system['id64']) for system in REVIEW_SYSTEMS]


async def _upsert_app_meta(conn: asyncpg.Connection) -> None:
    entries = (
        ('import_complete', 'true'),
        ('ratings_built', 'true'),
        ('grid_built', 'true'),
        ('clusters_built', 'false'),
        ('eddn_enabled', 'false'),
        ('schema_version', 'review-fixture-v2'),
        ('last_nightly_update', 'review-fixture'),
    )
    await conn.executemany(
        """
        INSERT INTO app_meta (key, value)
        VALUES ($1, $2)
        ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value,
            updated_at = NOW()
        """,
        entries,
    )


async def _upsert_systems(conn: asyncpg.Connection) -> None:
    rows = [
        (
            system['id64'],
            system['name'],
            system['x'],
            system['y'],
            system['z'],
            system['primary_economy'],
            system['secondary_economy'],
            system['population'],
            system['is_colonised'],
            system['security'],
            system['allegiance'],
            system['government'],
            system['main_star_type'],
            system['main_star_subtype'],
            True,
            system['body_count'],
            5,
            18,
        )
        for system in REVIEW_SYSTEMS
    ]
    await conn.executemany(
        """
        INSERT INTO systems (
          id64,
          name,
          x,
          y,
          z,
          primary_economy,
          secondary_economy,
          population,
          is_colonised,
          security,
          allegiance,
          government,
          main_star_type,
          main_star_subtype,
          has_body_data,
          body_count,
          data_quality,
          galaxy_region_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
        ON CONFLICT (id64) DO UPDATE
        SET name = EXCLUDED.name,
            x = EXCLUDED.x,
            y = EXCLUDED.y,
            z = EXCLUDED.z,
            primary_economy = EXCLUDED.primary_economy,
            secondary_economy = EXCLUDED.secondary_economy,
            population = EXCLUDED.population,
            is_colonised = EXCLUDED.is_colonised,
            security = EXCLUDED.security,
            allegiance = EXCLUDED.allegiance,
            government = EXCLUDED.government,
            main_star_type = EXCLUDED.main_star_type,
            main_star_subtype = EXCLUDED.main_star_subtype,
            has_body_data = EXCLUDED.has_body_data,
            body_count = EXCLUDED.body_count,
            data_quality = EXCLUDED.data_quality,
            galaxy_region_id = EXCLUDED.galaxy_region_id,
            rating_dirty = FALSE,
            cluster_dirty = FALSE,
            updated_at = NOW()
        """,
        rows,
    )


async def _upsert_bodies(conn: asyncpg.Connection) -> None:
    rows = []
    for system in REVIEW_SYSTEMS:
        for body in system['bodies']:
            rows.append(
                (
                    body['id'],
                    system['id64'],
                    body['name'],
                    body['body_type'],
                    body['subtype'],
                    body['is_main_star'],
                    body['distance_from_star'],
                    body['radius'],
                    body['mass'],
                    body['gravity'],
                    body['surface_temp'],
                    body['is_terraformable'],
                    body['is_landable'],
                    body['is_water_world'],
                    body['is_earth_like'],
                    body['is_ammonia_world'],
                    body['bio_signal_count'],
                    body['geo_signal_count'],
                    body['spectral_class'],
                    body['is_scoopable'],
                    body['estimated_mapping_value'],
                    body['estimated_scan_value'],
                )
            )
    await conn.executemany(
        """
        INSERT INTO bodies (
          id,
          system_id64,
          name,
          body_type,
          subtype,
          is_main_star,
          distance_from_star,
          radius,
          mass,
          gravity,
          surface_temp,
          is_terraformable,
          is_landable,
          is_water_world,
          is_earth_like,
          is_ammonia_world,
          bio_signal_count,
          geo_signal_count,
          spectral_class,
          is_scoopable,
          estimated_mapping_value,
          estimated_scan_value
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22)
        ON CONFLICT (id) DO UPDATE
        SET system_id64 = EXCLUDED.system_id64,
            name = EXCLUDED.name,
            body_type = EXCLUDED.body_type,
            subtype = EXCLUDED.subtype,
            is_main_star = EXCLUDED.is_main_star,
            distance_from_star = EXCLUDED.distance_from_star,
            radius = EXCLUDED.radius,
            mass = EXCLUDED.mass,
            gravity = EXCLUDED.gravity,
            surface_temp = EXCLUDED.surface_temp,
            is_terraformable = EXCLUDED.is_terraformable,
            is_landable = EXCLUDED.is_landable,
            is_water_world = EXCLUDED.is_water_world,
            is_earth_like = EXCLUDED.is_earth_like,
            is_ammonia_world = EXCLUDED.is_ammonia_world,
            bio_signal_count = EXCLUDED.bio_signal_count,
            geo_signal_count = EXCLUDED.geo_signal_count,
            spectral_class = EXCLUDED.spectral_class,
            is_scoopable = EXCLUDED.is_scoopable,
            estimated_mapping_value = EXCLUDED.estimated_mapping_value,
            estimated_scan_value = EXCLUDED.estimated_scan_value,
            updated_at = NOW()
        """,
        rows,
    )


async def _upsert_stations(conn: asyncpg.Connection) -> None:
    rows = []
    for system in REVIEW_SYSTEMS:
        for station in system['stations']:
            rows.append(
                (
                    station['id'],
                    system['id64'],
                    station['name'],
                    station['station_type'],
                    station['distance_from_star'],
                    station['body_name'],
                    station['landing_pad_size'],
                    station['has_market'],
                    station['has_shipyard'],
                    station['has_outfitting'],
                    station['has_refuel'],
                    station['has_repair'],
                    station['has_rearm'],
                    True,
                    station['primary_economy'],
                    station['secondary_economy'],
                    station['allegiance'],
                    station['government'],
                )
            )
    await conn.executemany(
        """
        INSERT INTO stations (
          id,
          system_id64,
          name,
          station_type,
          distance_from_star,
          body_name,
          landing_pad_size,
          has_market,
          has_shipyard,
          has_outfitting,
          has_refuel,
          has_repair,
          has_rearm,
          has_universal_cartographics,
          primary_economy,
          secondary_economy,
          allegiance,
          government
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
        ON CONFLICT (id) DO UPDATE
        SET system_id64 = EXCLUDED.system_id64,
            name = EXCLUDED.name,
            station_type = EXCLUDED.station_type,
            distance_from_star = EXCLUDED.distance_from_star,
            body_name = EXCLUDED.body_name,
            landing_pad_size = EXCLUDED.landing_pad_size,
            has_market = EXCLUDED.has_market,
            has_shipyard = EXCLUDED.has_shipyard,
            has_outfitting = EXCLUDED.has_outfitting,
            has_refuel = EXCLUDED.has_refuel,
            has_repair = EXCLUDED.has_repair,
            has_rearm = EXCLUDED.has_rearm,
            has_universal_cartographics = EXCLUDED.has_universal_cartographics,
            primary_economy = EXCLUDED.primary_economy,
            secondary_economy = EXCLUDED.secondary_economy,
            allegiance = EXCLUDED.allegiance,
            government = EXCLUDED.government,
            updated_at = NOW()
        """,
        rows,
    )


async def _upsert_ratings(conn: asyncpg.Connection) -> None:
    rows = []
    for system in REVIEW_SYSTEMS:
        rating = system['rating']
        rows.append(
            (
                system['id64'],
                rating['score'],
                rating['score_agriculture'],
                rating['score_refinery'],
                rating['score_industrial'],
                rating['score_hightech'],
                rating['score_military'],
                rating['score_tourism'],
                rating['score_extraction'],
                rating['economy_suggestion'],
                rating['elw_count'],
                rating['ww_count'],
                rating['ammonia_count'],
                rating['gas_giant_count'],
                int(rating.get('rocky_count', 0)),
                int(rating.get('metal_rich_count', 0)),
                int(rating.get('icy_count', 0)),
                int(rating.get('rocky_ice_count', 0)),
                int(rating.get('hmc_count', 0)),
                rating['landable_count'],
                rating['terraformable_count'],
                rating['bio_signal_total'],
                rating['geo_signal_total'],
                rating['neutron_count'],
                rating['black_hole_count'],
                rating['white_dwarf_count'],
                rating['slots'],
                rating['body_quality'],
                rating['compactness'],
                rating['signal_quality'],
                rating['orbital_safety'],
                rating['star_bonus'],
                json.dumps(rating['score_breakdown'], sort_keys=True),
                rating['rating_version'],
                _rating_confidence(rating.get('confidence')),
                rating['rationale'],
            )
        )
    await conn.executemany(
        """
        INSERT INTO ratings (
          system_id64,
          score,
          score_agriculture,
          score_refinery,
          score_industrial,
          score_hightech,
          score_military,
          score_tourism,
          score_extraction,
          economy_suggestion,
          elw_count,
          ww_count,
          ammonia_count,
          gas_giant_count,
          rocky_count,
          metal_rich_count,
          icy_count,
          rocky_ice_count,
          hmc_count,
          landable_count,
          terraformable_count,
          bio_signal_total,
          geo_signal_total,
          neutron_count,
          black_hole_count,
          white_dwarf_count,
          slots,
          body_quality,
          compactness,
          signal_quality,
          orbital_safety,
          star_bonus,
          score_breakdown,
          rating_version,
          confidence,
          rationale
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32, $33::jsonb, $34, $35, $36)
        ON CONFLICT (system_id64) DO UPDATE
        SET score = EXCLUDED.score,
            score_agriculture = EXCLUDED.score_agriculture,
            score_refinery = EXCLUDED.score_refinery,
            score_industrial = EXCLUDED.score_industrial,
            score_hightech = EXCLUDED.score_hightech,
            score_military = EXCLUDED.score_military,
            score_tourism = EXCLUDED.score_tourism,
            score_extraction = EXCLUDED.score_extraction,
            economy_suggestion = EXCLUDED.economy_suggestion,
            elw_count = EXCLUDED.elw_count,
            ww_count = EXCLUDED.ww_count,
            ammonia_count = EXCLUDED.ammonia_count,
            gas_giant_count = EXCLUDED.gas_giant_count,
            rocky_count = EXCLUDED.rocky_count,
            metal_rich_count = EXCLUDED.metal_rich_count,
            icy_count = EXCLUDED.icy_count,
            rocky_ice_count = EXCLUDED.rocky_ice_count,
            hmc_count = EXCLUDED.hmc_count,
            landable_count = EXCLUDED.landable_count,
            terraformable_count = EXCLUDED.terraformable_count,
            bio_signal_total = EXCLUDED.bio_signal_total,
            geo_signal_total = EXCLUDED.geo_signal_total,
            neutron_count = EXCLUDED.neutron_count,
            black_hole_count = EXCLUDED.black_hole_count,
            white_dwarf_count = EXCLUDED.white_dwarf_count,
            slots = EXCLUDED.slots,
            body_quality = EXCLUDED.body_quality,
            compactness = EXCLUDED.compactness,
            signal_quality = EXCLUDED.signal_quality,
            orbital_safety = EXCLUDED.orbital_safety,
            star_bonus = EXCLUDED.star_bonus,
            score_breakdown = EXCLUDED.score_breakdown,
            rating_version = EXCLUDED.rating_version,
            confidence = EXCLUDED.confidence,
            rationale = EXCLUDED.rationale,
            updated_at = NOW()
        """,
        rows,
    )


def _rating_confidence(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.95


async def _upsert_review_contracts(conn: asyncpg.Connection) -> None:
    entries = []
    for id64, contract in REVIEW_WAREHOUSE_CONTRACTS.items():
        entries.append((review_warehouse_contract_key(id64), json.dumps(contract, sort_keys=True)))
    for id64, contract in REVIEW_PROVENANCE_CONTRACTS.items():
        entries.append((review_provenance_contract_key(id64), json.dumps(contract, sort_keys=True)))
    await conn.executemany(
        """
        INSERT INTO app_meta (key, value)
        VALUES ($1, $2)
        ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value,
            updated_at = NOW()
        """,
        entries,
    )


async def _main() -> int:
    validate_review_runtime_env(os.environ)
    database_url = (os.environ.get('DATABASE_URL') or '').strip()
    if not database_url:
        raise ReviewSeedError('DATABASE_URL is required for review seed')
    pool = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=4, statement_cache_size=0)
    try:
        result = await ensure_review_seed(pool)
    finally:
        await pool.close()
    print(json.dumps({'ok': True, 'seed_counts': result, 'review_systems': list(review_system_names())}, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(_main()))
