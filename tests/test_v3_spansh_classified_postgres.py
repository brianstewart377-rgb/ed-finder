"""Opt-in PostgreSQL 18 rehearsal using a bounded, attributed Spansh slice.

Set EDFINDER_SPANSH_TEST_DATABASE_URL and EDFINDER_SPANSH_TEST_DATABASE=yes to
a dedicated local PostgreSQL cluster. The fixture creates and removes only a
new randomly named database; it never changes the supplied database or publishes.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
import zipfile

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import pytest

from tests.helpers import db_isolation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/importer/src"))


def _local_connect(dsn, **kwargs):
    settings = conninfo_to_dict(dsn)
    assert settings["host"] in {"127.0.0.1", "localhost", "::1"}
    return psycopg.connect(dsn, hostaddr="::1" if settings["host"] == "::1" else "127.0.0.1", **kwargs)


@pytest.fixture
def classified_database():
    target = db_isolation.confirmed_target_or_skip(
        dsn_env="EDFINDER_SPANSH_TEST_DATABASE_URL",
        confirm_env="EDFINDER_SPANSH_TEST_DATABASE",
        purpose="classified Spansh PostgreSQL rehearsal",
    )
    database = f"spansh_classified_test_{uuid4().hex[:16]}"
    with _local_connect(target.dsn, autocommit=True) as admin:
        assert 180000 <= admin.info.server_version < 190000
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        dsn = make_conninfo(target.dsn, dbname=database)
        try:
            with _local_connect(dsn, autocommit=True) as conn:
                conn.execute((ROOT / "sql/v3/migrations/001_v3_baseline.sql").read_text("utf-8"))
            yield dsn
        finally:
            # Only the database created above is removed, never the input target.
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))


@pytest.fixture
def classified_slice(tmp_path):
    # Existing repository evidence, attributed to https://www.spansh.co.uk/.
    # Unwrap the system endpoint envelope into the galaxy-dump array shape.
    source = ROOT / "tests/fixtures/ratings_v4_sources/spansh-system-dumps.zip"
    with zipfile.ZipFile(source) as archive:
        records = [json.loads(archive.read(name))["system"] for name in archive.namelist()]
    expected_colours = {}
    for ordinal, (source_fields, colour) in enumerate([
        ({"subType": "O (Blue-White) Star"}, "O"),
        ({"spectralClass": "B2 V"}, "B"),
        ({"SpectralClass": "A3"}, "A"),
        ({"StarType": "F"}, "F"),
        ({"subType": "G (White-Yellow) Star"}, "G"),
        ({"subType": "K (Yellow-Orange) Star"}, "K"),
        ({"subType": "M (Red dwarf) Star"}, "M"),
        ({"subType": "Neutron Star"}, "neutron"),
        ({"StarType": "DAZ"}, "white-dwarf"),
        ({"subType": "Black Hole"}, "black-hole"),
    ]):
        system_id = 900_000_000_000_000 + ordinal
        name = f"Synthetic Spansh classification {ordinal}"
        records.append({
            "id64": system_id, "name": name, "coords": {"x": ordinal, "y": 0, "z": 0},
            "bodies": [{"bodyId": 0, "name": name, "type": "Star", **source_fields}],
        })
        expected_colours[system_id] = colour

    # The explicit main star wins even though the companion has body ID/distance 0.
    explicit_id = 900_000_000_000_100
    records.append({
        "id64": explicit_id, "name": "Synthetic explicit main star",
        "coords": {"x": 100, "y": 0, "z": 0},
        "bodies": [
            {"bodyId": 0, "name": "Companion", "type": "Star", "StarType": "B", "distanceToArrival": 0},
            {"bodyId": 1, "name": "Primary", "type": "Star", "StarType": "K", "distanceToArrival": 100, "isMainStar": True},
            {"bodyId": 2, "name": "Planet", "PlanetClass": "Water world"},
        ],
    })
    expected_colours[explicit_id] = "K"
    barycentre_id = 900_000_000_000_101
    records.append({
        "id64": barycentre_id, "name": "Synthetic barycentre first",
        "coords": {"x": 101, "y": 0, "z": 0},
        "bodies": [
            {"bodyId": 0, "name": "Barycentre", "type": "Barycentre"},
            {"bodyId": 1, "name": "Arrival star", "type": "Star", "subType": "M (Red dwarf) Star", "distanceToArrival": 0},
            {"bodyId": 2, "name": "Unknown source class", "subType": "Future exotic body"},
        ],
    })
    expected_colours[barycentre_id] = "M"
    path = tmp_path / "spansh-classified-slice.json.gz"
    path.write_bytes(gzip.compress(json.dumps(records).encode("utf-8"), mtime=0))
    metadata = tmp_path / "spansh-classified-slice.metadata.json"
    metadata.write_text(json.dumps({
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
        "retrieved_at": "2026-09-19T00:00:00Z",
        "source_url": "https://www.spansh.co.uk/",
        "attribution": "Spansh source fixture with explicitly synthetic classification cases",
    }), encoding="utf-8")
    return path, metadata, records, expected_colours


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.requires_postgres
def test_classified_copy_resolves_map_colours_and_public_codes(classified_database, classified_slice):
    from v3_spansh.pipeline import ArtifactRegistration
    from v3_spansh_classified import VERSION
    from v3_spansh_classified.pipeline import ClassifiedImportConfig, ClassifiedSpanshPipeline, code_hash

    path, metadata, records, expected_colours = classified_slice
    with _local_connect(classified_database) as conn:
        # IDs are internal. Classification must resolve by public_code.
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO v3_vocab.body_type(body_type_id,public_code,display_name) VALUES (%s,%s,%s)",
                [(101, "star", "Star"), (102, "planet", "Planet"),
                 (103, "barycentre", "Barycentre"), (104, "belt_cluster", "Belt Cluster")],
            )
    pipeline = ClassifiedSpanshPipeline(
        classified_database, ArtifactRegistration.load(path, metadata),
        ClassifiedImportConfig(generation_key="spansh_classification_test", target_systems=len(records),
                               max_systems=len(records), chunk_systems=4),
    )
    result = pipeline.run()
    assert result["systems"] == len(records)
    assert result["dry_run"] is False
    assert result["published"] is False
    schema = sql.Identifier(result["relation_schema"])
    with _local_connect(classified_database) as conn:
        assert conn.execute("SHOW session_replication_role").fetchone()[0] == "origin"
        # Exercise the same selection contract as both map.py lateral joins.
        colour_rows = conn.execute(sql.SQL("""
            SELECT s.id64, body.spectral_class FROM {schema}.systems s
            LEFT JOIN LATERAL (
                SELECT b.spectral_class FROM {schema}.bodies b
                WHERE b.system_id64=s.id64 AND b.is_main_star
                ORDER BY b.body_pk LIMIT 1
            ) body ON TRUE
            """).format(schema=schema)).fetchall()
        actual = dict(colour_rows)
        assert {key: actual[key] for key in expected_colours} == expected_colours
        assert all(value is not None for value in actual.values())
        assert conn.execute(sql.SQL("""
            SELECT count(*) FROM {schema}.bodies b
            JOIN v3_vocab.body_type t USING(body_type_id)
            WHERE b.is_main_star AND t.public_code <> 'star'
            """).format(schema=schema)).fetchone()[0] == 0
        assert conn.execute(sql.SQL("""
            SELECT count(*) FROM (
                SELECT system_id64 FROM {schema}.bodies WHERE is_main_star
                GROUP BY system_id64 HAVING count(*) <> 1
            ) invalid
            """).format(schema=schema)).fetchone()[0] == 0
        classes = dict(conn.execute(sql.SQL("""
            SELECT b.name,t.public_code FROM {schema}.bodies b
            LEFT JOIN v3_vocab.body_type t USING(body_type_id)
            WHERE b.system_id64 = %s
            """).format(schema=schema), (900_000_000_000_100,)).fetchall())
        assert classes == {"Companion": "star", "Primary": "star", "Planet": "planet"}
        assert conn.execute(sql.SQL("SELECT count(*) FROM {}.bodies WHERE body_type_id < 101").format(schema)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM v3_source.unmapped_vocabulary WHERE raw_token=%s",
                            ("Future exotic body",)).fetchone()[0] >= 1
        assert conn.execute(sql.SQL("""
            SELECT count(*) FROM {}.bodies
            WHERE system_id64=ANY(%s) AND body_type_id IS NULL
            """).format(schema), ([row["id64"] for row in records[:12]],)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM v3_meta.current_canonical_generation").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM v3_meta.canonical_publication_audit").fetchone()[0] == 0
        state, receipt = conn.execute(
            "SELECT lifecycle_state,validation_receipt FROM v3_meta.canonical_generation WHERE generation_id=%s",
            (pipeline.generation_id,),
        ).fetchone()
        assert state == "READY"
        assert receipt == result
        assert conn.execute("""
            SELECT importer_version,normalizer_version,importer_code_sha256,normalizer_sha256,run_state
            FROM v3_source.source_run WHERE source_run_id=%s
            """, (pipeline.source_run_id,)).fetchone() == (VERSION, VERSION, code_hash(), code_hash(), "SUCCEEDED")
        foreign_keys, validated = conn.execute("""
            SELECT count(*),bool_and(c.convalidated)
            FROM pg_catalog.pg_constraint c
            JOIN pg_catalog.pg_namespace n ON n.oid=c.connamespace
            WHERE n.nspname=%s AND c.contype='f'
            """, (result["relation_schema"],)).fetchone()
        assert foreign_keys > 0 and validated
        before_bodies = conn.execute(sql.SQL("SELECT count(*) FROM {}.bodies").format(schema)).fetchone()[0]
        with pytest.raises(ValueError, match="fresh generation key"):
            pipeline.run()
        assert conn.execute(sql.SQL("SELECT count(*) FROM {}.bodies").format(schema)).fetchone()[0] == before_bodies
        assert conn.execute("SELECT count(*) FROM v3_meta.canonical_generation").fetchone()[0] == 1


def test_classified_cli_dry_run_uses_no_database(classified_slice, monkeypatch):
    path, metadata, records, expected_colours = classified_slice
    monkeypatch.delenv("SPANSH_CLASSIFIED_TEST_DSN", raising=False)
    process = subprocess.run([
        sys.executable, str(ROOT / "scripts/dev/import_spansh_classified_slice.py"),
        "--artifact", str(path), "--artifact-metadata", str(metadata),
        "--max-systems", str(len(records)), "--dry-run",
    ], check=True, capture_output=True, text=True)
    result = json.loads(process.stdout)
    assert result["dry_run"] is True
    assert result["published"] is False
    assert result["source"] == "Spansh"
    assert result["systems"] == len(records)
    assert result["main_stars"] == len(records)
    assert result["systems_without_main_star"] == 0
    assert set(expected_colours.values()) <= set(result["spectral_classes"])
    assert result["body_type_counts"]["barycentre"] > 0
    assert result["unclassified_bodies"] == 1
