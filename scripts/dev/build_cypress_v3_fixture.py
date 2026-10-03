"""Generate the curated Cypress V3 canonical fixture (plan Task 2).

The browser product-journey asserts two specific systems by id64: Achenar
``10477373803000`` (detail view shows a "Primary star" body) and
"V3 Lossless Reach" ``9007199254740993`` (id64 > 2^53, the lossless big-int
case). This generator derives a small, checksum-locked canonical fixture that
carries those id64s by SUBSETTING the proven Ratings V4 source fixture
(``tests/fixtures/ratings_v4_sources``) and rewriting only the system-level
id64/name of the chosen systems -- so the curated fixture inherits the
template's exact, pipeline-valid body/ring/signal inventory (and therefore
passes ``adapt_retained_chunk`` and the full derived build unchanged).

Run once locally; the output under ``tests/fixtures/cypress_v3_sources`` is
committed and read-only in CI.

    apps/api/.venv/bin/python scripts/dev/build_cypress_v3_fixture.py \
        --out tests/fixtures/cypress_v3_sources
"""
from __future__ import annotations

import argparse
import copy
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'apps/api/src'))

TEMPLATE_DIR = ROOT / 'tests/fixtures/ratings_v4_sources'

# Template system id64 -> (curated id64, curated name, (x_ly, y_ly, z_ly)). The
# third selected system is kept verbatim as a distinct extra search result.
#  - Sol (has an is_main_star body) becomes journey Achenar.
#  - Alioth becomes the lossless big-int system.
# Coordinates are rewritten to EXACTLY match the legacy journey records
# (sql/seed_preview.sql Achenar; cypress-parity.yml lossless top-up) so the
# legacy<->V3 parity gate holds spatially, not just by name -- autocomplete/detail
# read legacy coords while Finder renders V3 coords, and they must agree.
REWRITE: dict[int, tuple[int, str, tuple[float, float, float]]] = {
    10477373803: (10477373803000, 'Achenar', (67.50, -119.47, 24.84)),
    1109989017963: (9007199254740993, 'V3 Lossless Reach', (18.25, -7.5, 42.75)),
}
THIRD_SYSTEM = 158872029  # kept verbatim (distinct 3rd result)
SELECTED = (*REWRITE, THIRD_SYSTEM)

# Deterministic zip member timestamp so the committed artifact (and its
# checksum) is byte-reproducible on re-run. Date.now() is deliberately avoided.
_ZIP_DATE = (2026, 1, 1, 0, 0, 0)


def _canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


def _rewrite_system(system: dict) -> dict:
    out = copy.deepcopy(system)
    if out['id64'] in REWRITE:
        new_id, new_name, (x_ly, y_ly, z_ly) = REWRITE[out['id64']]
        out['id64'] = new_id
        out['name'] = new_name
        # system_search is built from these canonical coords (scripts/v3_system_search
        # selects s.x_ly/y_ly/z_ly); grid_* are not read by the search product.
        out['x_ly'], out['y_ly'], out['z_ly'] = x_ly, y_ly, z_ly
    return out


def _rewrite_system_id_field(row: dict, field: str = 'system_id64') -> dict:
    out = copy.deepcopy(row)
    if out.get(field) in REWRITE:
        out[field] = REWRITE[out[field]][0]
    return out


def build(template_dir: Path) -> tuple[dict, bytes, list[dict]]:
    """Return (curated_canonical, source_metadata_bytes, curated_zip_members)."""
    canonical = json.loads((template_dir / 'canonical.json').read_bytes())
    metadata_bytes = (template_dir / 'source-metadata.json').read_bytes()

    selected = set(SELECTED)
    systems = [_rewrite_system(s) for s in canonical['systems'] if s['id64'] in selected]
    if len(systems) != len(SELECTED):
        missing = selected - {s['id64'] for s in canonical['systems']}
        raise SystemExit(f'template is missing selected system id64s: {sorted(missing)}')

    bodies = [_rewrite_system_id_field(b) for b in canonical['bodies']
              if b['system_id64'] in selected]
    selected_body_pks = {b['body_pk'] for b in bodies}

    # Rebuild extras: vocab verbatim (FKs need the whole vocabulary); gen-schema
    # relations filtered to the selected systems/bodies, rewriting system_id64
    # where the relation carries it (rings, body_parent_evidence).
    system_keyed = {'rings', 'body_parent_evidence'}
    extras = []
    for extra in canonical['extras']:
        if extra['schema'] == 'v3_vocab':
            extras.append(copy.deepcopy(extra))
            continue
        rows = extra['rows']
        if extra['relation'] in system_keyed:
            kept = [_rewrite_system_id_field(r) for r in rows if r['system_id64'] in selected]
        elif rows and 'body_pk' in rows[0]:
            kept = [copy.deepcopy(r) for r in rows if r['body_pk'] in selected_body_pks]
        else:
            kept = [copy.deepcopy(r) for r in rows]
        extras.append({'schema': extra['schema'], 'relation': extra['relation'], 'rows': kept})

    curated = copy.deepcopy(canonical)
    curated['systems'] = systems
    curated['bodies'] = bodies
    curated['extras'] = extras

    # Spansh dump members: keep each selected system's member verbatim except
    # the rewritten id64/name on the two journey systems.
    members = []
    with ZipFile(template_dir / 'spansh-system-dumps.zip') as archive:
        for name in archive.namelist():
            payload = json.loads(archive.read(name))
            old_id = payload['system']['id64']
            if old_id not in selected:
                continue
            if old_id in REWRITE:
                new_id, new_name, coords = REWRITE[old_id]
                payload['system']['id64'] = new_id
                payload['system']['name'] = new_name
                # Keep the raw dump's coords consistent with the canonical rewrite
                # (not read by the build, but avoids a misleading fixture artifact).
                if isinstance(payload['system'].get('coords'), dict):
                    payload['system']['coords'] = {'x': coords[0], 'y': coords[1], 'z': coords[2]}
            members.append(payload)
    return curated, metadata_bytes, members


def _zip_bytes(members: list[dict]) -> bytes:
    buffer = io.BytesIO()
    # Sort by id64 so member order (and thus the archive bytes) is deterministic.
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
        for payload in sorted(members, key=lambda m: m['system']['id64']):
            info = ZipInfo(f"{payload['system']['id64']}.json", date_time=_ZIP_DATE)
            # writestr() honours the ZipInfo's own compress_type, which defaults
            # to ZIP_STORED regardless of the ZipFile default -- so set it
            # explicitly or the committed fixture is multi-MB uncompressed JSON.
            info.compress_type = ZIP_DEFLATED
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
    ids = {s['id64']: s['name'] for s in curated['systems']}
    print(f'wrote curated cypress v3 fixture to {out_dir}')
    print(f'  systems ({len(ids)}): {ids}')
    print(f'  bodies: {len(curated["bodies"])}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='tests/fixtures/cypress_v3_sources',
                        help='output fixture directory (relative to repo root)')
    args = parser.parse_args()
    out_dir = (ROOT / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    write_fixture(out_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
