"""Generate the independent Review Lab V3 canonical fixture (Phase 2 step 1).

The fixture contains three fictional Review-Lab-only systems. This generator
derives the small, checksum-locked corpus by SUBSETTING the proven Ratings V4
source fixture (``tests/fixtures/ratings_v4_sources``) and rewriting every
selected system's id64, name, coordinates, embedded body/ring names, and
dependent identity references. The resulting canonical and raw inventories
therefore retain the template's pipeline-valid shape without sharing the
Cypress product-journey fixture.

Run once locally; the output under
``tests/fixtures/review_lab_v3_sources`` is committed and read-only in CI.

    apps/api/.venv/bin/python scripts/dev/build_review_lab_v3_fixture.py \
        --out tests/fixtures/review_lab_v3_sources
"""
from __future__ import annotations

import argparse
import copy
from hashlib import sha256
import io
import json
from math import floor
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'apps/api/src'))
sys.path.insert(0, str(ROOT / 'apps/importer/src'))

from v3_spansh.contracts import GRID_EDGE_LY, macro_grid_key  # noqa: E402

TEMPLATE_DIR = ROOT / 'tests/fixtures/ratings_v4_sources'

# Template system id64 -> (Review id64, Review name, (x_ly, y_ly, z_ly)).
# Review Wiring and Review Aggregate share density-pyramid cells at levels 0-2
# (2560, 1280 and 640 ly) and split at levels 3-6 (320 through 40 ly).
# Review Fallback is in a different cell from both at every configured level.
REWRITE: dict[int, tuple[int, str, tuple[float, float, float]]] = {
    164098653: (9100000000001, 'Review Wiring', (100.0, 100.0, 100.0)),
    158872029: (9100000000002, 'Review Aggregate', (500.0, 100.0, 100.0)),
    7780836610810: (9100000000003, 'Review Fallback', (3000.0, 100.0, 100.0)),
}
SELECTED = tuple(REWRITE)

# Explicit member metadata avoids platform defaults. Compressed archive bytes
# may still vary between zlib versions, so content is the portability contract.
_ZIP_DATE = (2026, 1, 1, 0, 0, 0)
_ZIP_CREATE_SYSTEM = 3
_ZIP_EXTERNAL_ATTR = 0o644 << 16
_ZIP_COMPRESSION = ZIP_DEFLATED


def _canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


def cell_index(coords: tuple[float, float, float], cell_size_ly: float) -> tuple[int, int, int]:
    """Apply the density builder's component-wise ``floor(coord / size)`` formula."""
    return tuple(floor(coordinate / cell_size_ly) for coordinate in coords)


def _rewrite_embedded_values(value):
    """Rewrite selected identities and embedded system-name substrings.

    A template system's id64 is also used as its main body's body_pk/source
    id64 and by dependent parent/FK rows. Rewriting exact integer values
    recursively preserves those relationships while ensuring no template
    identity remains in the independent fixture. Raw source payloads also use
    system names in body, ring, faction, and station strings, so strings need a
    recursive substring rewrite rather than a field-specific name update.
    """
    if isinstance(value, dict):
        return {key: _rewrite_embedded_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_embedded_values(item) for item in value]
    if type(value) is int and value in REWRITE:
        return REWRITE[value][0]
    if isinstance(value, str):
        for old_id, (_, new_name, _) in REWRITE.items():
            old_name = _TEMPLATE_NAMES[old_id]
            value = value.replace(old_name, new_name)
        return value
    return value


def _rewrite_system(system: dict) -> dict:
    old_id = system['id64']
    new_id, new_name, (x_ly, y_ly, z_ly) = REWRITE[old_id]
    out = _rewrite_embedded_values(copy.deepcopy(system))
    out['id64'] = new_id
    out['name'] = new_name
    # Keep the map viewport's coarse-grid prefilter aligned with the exact
    # canonical coordinates, using the same contract as the real importer.
    out['x_ly'], out['y_ly'], out['z_ly'] = x_ly, y_ly, z_ly
    grid_x, grid_y, grid_z = (
        floor(coordinate / GRID_EDGE_LY) for coordinate in (x_ly, y_ly, z_ly)
    )
    out['grid_x'], out['grid_y'], out['grid_z'] = grid_x, grid_y, grid_z
    out['macro_grid_key'] = macro_grid_key(grid_x, grid_y, grid_z)
    return out


_TEMPLATE_NAMES: dict[int, str] = {}


def build(template_dir: Path) -> tuple[dict, bytes, list[dict]]:
    """Return (curated_canonical, source_metadata_bytes, curated_zip_members)."""
    canonical = json.loads((template_dir / 'canonical.json').read_bytes())
    metadata_bytes = (template_dir / 'source-metadata.json').read_bytes()

    selected = set(SELECTED)
    selected_systems = [s for s in canonical['systems'] if s['id64'] in selected]
    if len(selected_systems) != len(SELECTED):
        missing = selected - {s['id64'] for s in canonical['systems']}
        raise SystemExit(f'template is missing selected system id64s: {sorted(missing)}')
    _TEMPLATE_NAMES.clear()
    _TEMPLATE_NAMES.update({system['id64']: system['name'] for system in selected_systems})

    systems = [_rewrite_system(system) for system in selected_systems]
    selected_bodies = [body for body in canonical['bodies']
                       if body['system_id64'] in selected]
    selected_body_pks = {body['body_pk'] for body in selected_bodies}
    bodies = [_rewrite_embedded_values(copy.deepcopy(body)) for body in selected_bodies]

    # Rebuild extras: vocab verbatim (FKs need the whole vocabulary); gen-schema
    # relations filtered to the selected systems/bodies. Recursive identity
    # rewriting covers system_id64 in rings/body_parent_evidence and body-PK
    # references in every dependent relation.
    system_keyed = {'rings', 'body_parent_evidence'}
    extras = []
    for extra in canonical['extras']:
        if extra['schema'] == 'v3_vocab':
            extras.append(copy.deepcopy(extra))
            continue
        rows = extra['rows']
        if extra['relation'] in system_keyed:
            kept = [row for row in rows if row['system_id64'] in selected]
        elif rows and 'body_pk' in rows[0]:
            kept = [row for row in rows if row['body_pk'] in selected_body_pks]
        else:
            kept = list(rows)
        extras.append({
            'schema': extra['schema'],
            'relation': extra['relation'],
            'rows': _rewrite_embedded_values(copy.deepcopy(kept)),
        })

    curated = copy.deepcopy(canonical)
    curated['systems'] = systems
    curated['bodies'] = bodies
    curated['extras'] = extras
    curated['requested_systems'] = [system['name'] for system in systems]

    # Spansh dump members: keep each selected system's complete source member,
    # rewriting the identity/name everywhere and coordinates at system level.
    members = []
    with ZipFile(template_dir / 'spansh-system-dumps.zip') as archive:
        for name in archive.namelist():
            payload = json.loads(archive.read(name))
            old_id = payload['system']['id64']
            if old_id not in selected:
                continue
            new_id, new_name, coords = REWRITE[old_id]
            payload = _rewrite_embedded_values(payload)
            payload['system']['id64'] = new_id
            payload['system']['name'] = new_name
            if isinstance(payload['system'].get('coords'), dict):
                payload['system']['coords'] = {
                    'x': coords[0], 'y': coords[1], 'z': coords[2],
                }
            members.append(payload)
    return curated, metadata_bytes, members


def _zip_bytes(members: list[dict]) -> bytes:
    buffer = io.BytesIO()
    # Sort by id64 so member order (and thus the archive bytes) is deterministic.
    with ZipFile(buffer, 'w', _ZIP_COMPRESSION) as archive:
        for payload in sorted(members, key=lambda member: member['system']['id64']):
            info = ZipInfo(f"{payload['system']['id64']}.json", date_time=_ZIP_DATE)
            # writestr() honours the ZipInfo's own compress_type, which defaults
            # to ZIP_STORED regardless of the ZipFile default.
            info.create_system = _ZIP_CREATE_SYSTEM
            info.external_attr = _ZIP_EXTERNAL_ATTR
            info.compress_type = _ZIP_COMPRESSION
            archive.writestr(info, _canonical_bytes(payload))
    return buffer.getvalue()


def write_fixture(out_dir: Path) -> None:
    curated, metadata_bytes, members = build(TEMPLATE_DIR)
    template_manifest = json.loads((TEMPLATE_DIR / 'manifest.json').read_bytes())

    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        'canonical.json': _canonical_bytes(curated),
        'source-metadata.json': metadata_bytes,
        'spansh-system-dumps.zip': _zip_bytes(members),
    }
    for name, data in files.items():
        (out_dir / name).write_bytes(data)
    manifest = {
        'schema_version': template_manifest['schema_version'],
        'files_sha256': {name: sha256(data).hexdigest() for name, data in files.items()},
    }
    (out_dir / 'manifest.json').write_bytes(_canonical_bytes(manifest))
    ids = {system['id64']: system['name'] for system in curated['systems']}
    print(f'wrote curated review lab v3 fixture to {out_dir}')
    print(f'  systems ({len(ids)}): {ids}')
    print(f'  bodies: {len(curated["bodies"])}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='tests/fixtures/review_lab_v3_sources',
                        help='output fixture directory (relative to repo root)')
    args = parser.parse_args()
    out_dir = (ROOT / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    write_fixture(out_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
