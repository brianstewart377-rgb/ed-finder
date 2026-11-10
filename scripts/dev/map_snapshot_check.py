"""Local, fail-closed checks for an operator-prepared map test archive.

This tool never connects to production and never restores an archive. It checks
the bytes and archive inventory before the separate local restore step, then
checks published pointers and map data in the isolated Docker database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


FORMAT = "edfinder-map-snapshot/v1"
SCHEMA = re.compile(r"^v3_gen_[a-z][a-z0-9_]{0,30}$")
HEX_SHA256 = re.compile(r"^[a-f0-9]{64}$")
UUID = re.compile(r"^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$")
DATA_LINE = re.compile(r"^\d+; \d+ \d+ TABLE DATA (\S+) (\S+) ")
ALLOWED_SCHEMAS = {"v3_meta", "v3_source", "v3_vocab", "v3_spatial", "v3_derived"}
REQUIRED_RELATIONS = {
    "v3_meta.canonical_generation",
    "v3_meta.current_canonical_generation",
    "v3_meta.derived_generation",
    "v3_meta.current_derived_generation",
    "v3_meta.derived_product",
    "v3_spatial.spatial_generation",
    "v3_spatial.current_spatial_generation",
    "v3_spatial.cell_level",
    "v3_spatial.cell_summary",
    "v3_derived.system_search",
    "v3_derived.system_archetype",
}


def command(*args: str) -> str:
    process = subprocess.run(args, text=True, capture_output=True, check=False)
    if process.returncode:
        raise ValueError(f"{args[0]} failed: {process.stderr.strip()}")
    return process.stdout


def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("format") != FORMAT:
        raise ValueError("unknown snapshot manifest format")
    if not HEX_SHA256.fullmatch(str(manifest.get("sha256", ""))):
        raise ValueError("manifest needs a lowercase SHA-256")
    for key in ("generation_id", "spatial_generation_id", "derived_generation_id"):
        if not UUID.fullmatch(str(manifest.get(key, ""))):
            raise ValueError(f"invalid {key}")
    if not SCHEMA.fullmatch(str(manifest.get("relation_schema", ""))):
        raise ValueError("invalid canonical relation_schema")
    version = manifest.get("spatial_pyramid_version")
    if not isinstance(version, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", version):
        raise ValueError("invalid spatial_pyramid_version")
    for key in (
        "source_system_count", "level", "level_cell_count",
        "canonical_publication_sequence", "spatial_publication_sequence",
        "derived_publication_sequence",
    ):
        value = manifest.get(key)
        if type(value) is not int or value < (0 if key == "level" else 1):
            raise ValueError(f"invalid {key}")
    timestamp = manifest.get("captured_at")
    try:
        captured = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise ValueError("captured_at must be an ISO 8601 UTC timestamp") from error
    if captured.tzinfo is None or captured.utcoffset().total_seconds() != 0:
        raise ValueError("captured_at must be UTC")
    now = datetime.now(timezone.utc)
    if captured > now:
        raise ValueError("captured_at is in the future")
    if now - captured > timedelta(days=30):
        raise ValueError("snapshot is over 30 days old; refresh it for release acceptance")
    if manifest.get("coverage_level") not in ("camera-path", "whole-galaxy"):
        raise ValueError("coverage_level must be camera-path or whole-galaxy")
    paths = manifest.get("camera_paths")
    if not isinstance(paths, list) or not paths or not all(
        isinstance(item, str) and item for item in paths
    ):
        raise ValueError("camera_paths must identify the recorded journeys")
    relations = manifest.get("data_relations")
    if not isinstance(relations, list) or not all(isinstance(item, str) for item in relations):
        raise ValueError("data_relations must be an explicit list")
    if len(relations) != len(set(relations)):
        raise ValueError("duplicate data_relations")
    return manifest


def data_relations(archive_listing: str) -> set[str]:
    relations: set[str] = set()
    for line in archive_listing.splitlines():
        if re.search(r"\b(?:MATERIALIZED VIEW DATA|BLOBS?|LARGE OBJECT)\b", line):
            raise ValueError("archive contains payload outside the reviewed TABLE DATA inventory")
        match = DATA_LINE.match(line)
        if match:
            schema, table = match.groups()
            relation = f"{schema}.{table}"
            if relation in relations:
                raise ValueError(f"duplicate TABLE DATA entry: {relation}")
            relations.add(relation)
    if not relations:
        raise ValueError("no TABLE DATA entries in archive")
    return relations


def check_archive(manifest: dict, dump: Path, compose: Path) -> None:
    digest = hashlib.sha256()
    with dump.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != manifest["sha256"]:
        raise ValueError("archive SHA-256 does not match manifest")
    container_dump = "/tmp/map-snapshot.dump"
    container_digest = command(
        "docker", "compose", "-f", str(compose), "exec", "-T", "map-postgres",
        "sha256sum", container_dump,
    ).split()[0]
    if container_digest != manifest["sha256"]:
        raise ValueError("container archive SHA-256 does not match manifest")
    relations = data_relations(command(
        "docker", "compose", "-f", str(compose), "exec", "-T", "map-postgres",
        "pg_restore", "--list", container_dump,
    ))
    for relation in relations:
        schema = relation.split(".", 1)[0]
        if schema not in ALLOWED_SCHEMAS and schema != manifest["relation_schema"]:
            raise ValueError(f"unapproved TABLE DATA schema: {relation}")
    if not REQUIRED_RELATIONS <= relations:
        raise ValueError(f"missing map data relations: {sorted(REQUIRED_RELATIONS - relations)}")
    generation_relations = {
        f"{manifest['relation_schema']}.systems",
        f"{manifest['relation_schema']}.bodies",
    }
    if not generation_relations <= relations:
        raise ValueError("archive lacks published generation systems/bodies")
    if relations != set(manifest["data_relations"]):
        raise ValueError("TABLE DATA inventory differs from reviewed manifest")
    print(
        f"Archive verified: {len(relations)} reviewed data relations, "
        f"SHA-256 {digest.hexdigest()}"
    )


def local_sql(compose: Path, sql: str) -> str:
    return command(
        "docker", "compose", "-f", str(compose), "exec", "-T", "map-postgres",
        "psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-U", "map_test_user",
        "-d", "edfinder_map_test", "-c", sql,
    ).strip()


def check_local(manifest: dict, compose: Path) -> None:
    pointer_sql = """
        SELECT json_build_object(
          'generation_id', c.generation_id,
          'canonical_publication_sequence', c.publication_sequence,
          'relation_schema', g.relation_schema,
          'canonical_state', g.lifecycle_state,
          'spatial_generation_id', p.spatial_generation_id,
          'spatial_publication_sequence', p.publication_sequence,
          'spatial_pyramid_version', s.pyramid_version,
          'derived_generation_id', d.derived_generation_id,
          'derived_publication_sequence', d.publication_sequence,
          'derived_state', dg.lifecycle_state,
          'finder_products_ready', (SELECT count(*) FROM v3_meta.derived_product f
            WHERE f.derived_generation_id = d.derived_generation_id
              AND f.product_code IN ('system_search', 'system_archetype')
              AND f.lifecycle_state = 'READY' AND f.published_at IS NOT NULL),
          'source_system_count', s.expected_systems,
          'spatial_canonical_generation_id', s.canonical_generation_id,
          'spatial_state', s.lifecycle_state,
          'level_cell_count', (SELECT count(*) FROM v3_spatial.cell_summary x
            WHERE x.spatial_generation_id = p.spatial_generation_id
              AND x.level = {level})
        ) FROM v3_meta.current_canonical_generation c
        JOIN v3_meta.canonical_generation g USING (generation_id)
        CROSS JOIN v3_spatial.current_spatial_generation p
        JOIN v3_spatial.spatial_generation s USING (spatial_generation_id)
        CROSS JOIN v3_meta.current_derived_generation d
        JOIN v3_meta.derived_generation dg USING (derived_generation_id)
        WHERE c.singleton AND p.singleton AND d.singleton
    """.format(level=manifest["level"])
    raw = local_sql(compose, pointer_sql)
    if not raw:
        raise ValueError("local database has no paired published pointers")
    state = json.loads(raw)
    for key in (
        "generation_id", "canonical_publication_sequence", "relation_schema",
        "spatial_generation_id", "spatial_publication_sequence",
        "spatial_pyramid_version", "derived_generation_id",
        "derived_publication_sequence", "source_system_count", "level_cell_count",
    ):
        if state[key] != manifest[key]:
            raise ValueError(f"local {key} differs: {state[key]} != {manifest[key]}")
    if state["spatial_canonical_generation_id"] != manifest["generation_id"]:
        raise ValueError("spatial pyramid points to another canonical generation")
    if state["canonical_state"] != "PUBLISHED":
        raise ValueError("canonical generation is not PUBLISHED")
    if state["spatial_state"] != "PUBLISHED":
        raise ValueError("spatial pyramid is not PUBLISHED")
    if state["derived_state"] != "PUBLISHED" or state["finder_products_ready"] != 2:
        raise ValueError("Finder products are not published on the current derived generation")
    schema = manifest["relation_schema"]  # validated identifier, never user-supplied SQL
    canary_sql = f"""
        SELECT json_build_object(
          'achenar', EXISTS(SELECT 1 FROM {schema}.systems
            WHERE id64 = 10477373803000),
          'achenar_main_star', EXISTS(SELECT 1 FROM {schema}.bodies
            WHERE system_id64 = 10477373803000 AND is_main_star),
          'nearby_stars', (SELECT count(*) FROM (
            SELECT 1 FROM {schema}.systems s
            CROSS JOIN (SELECT x_ly, y_ly, z_ly FROM {schema}.systems
              WHERE id64 = 10477373803000) a
            WHERE s.grid_x BETWEEN floor((a.x_ly - 500) / 10) AND floor((a.x_ly + 500) / 10)
              AND s.grid_y BETWEEN floor((a.y_ly - 500) / 10) AND floor((a.y_ly + 500) / 10)
              AND s.grid_z BETWEEN floor((a.z_ly - 500) / 10) AND floor((a.z_ly + 500) / 10)
              AND s.x_ly BETWEEN a.x_ly - 500 AND a.x_ly + 500
              AND s.y_ly BETWEEN a.y_ly - 500 AND a.y_ly + 500
              AND s.z_ly BETWEEN a.z_ly - 500 AND a.z_ly + 500
            LIMIT 101) sampled)
        )
    """
    canary = json.loads(local_sql(compose, canary_sql))
    if not canary["achenar"] or not canary["achenar_main_star"] or canary["nearby_stars"] < 101:
        raise ValueError("local Achenar catalogue is missing or too sparse")
    print("Local published pointers, density and Achenar catalogue verified")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("archive", "local"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dump", type=Path)
    parser.add_argument("--compose", type=Path, default=Path("docker-compose.map-test.yml"))
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        if args.mode == "archive":
            if args.dump is None:
                parser.error("archive mode needs --dump")
            check_archive(manifest, args.dump, args.compose)
        else:
            check_local(manifest, args.compose)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Map snapshot check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

