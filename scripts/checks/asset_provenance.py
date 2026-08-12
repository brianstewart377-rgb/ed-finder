#!/usr/bin/env python3
"""Validate ED-Finder's asset provenance and public-file inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_RELATIVE_PATH = Path('assets/PROVENANCE.json')
SCHEMA_RELATIVE_PATH = Path('assets/PROVENANCE.schema.json')
NOTICES_RELATIVE_PATH = Path('THIRD_PARTY_NOTICES.md')
PUBLIC_RELATIVE_PATH = Path('frontend/public')

REQUIRED_TOP_LEVEL_FIELDS = {
    '$schema',
    'schema_version',
    'audit_date',
    'policy',
    'entries',
}
REQUIRED_ENTRY_FIELDS = {
    'filename',
    'asset_type',
    'distribution',
    'source_kind',
    'source_url',
    'license',
    'creator',
    'frontier_derived',
    'attribution_text',
    'approval_date',
    'verification_method',
    'sha256',
    'rights_status',
    'commercial_use_approved',
    'notice_reference',
}
ASSET_TYPES = {
    'data',
    'font',
    'image',
    'license_text',
    'script',
    'shader_source',
    'third_party_code_adaptation',
}
DISTRIBUTIONS = {'bundled_public', 'bundled_source', 'runtime_external'}
SOURCE_KINDS = {
    'original',
    'open_source',
    'open_licensed_media',
    'frontier_game',
    'community_creator',
    'unknown',
}
RIGHTS_STATUSES = {'approved', 'noncommercial_only', 'unresolved'}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _parse_iso_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _is_https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == 'https' and bool(parsed.netloc)


def _physical_filename(filename: str) -> str:
    return filename.split('#', 1)[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def collect_public_files(root: Path = ROOT) -> set[str]:
    public_root = root / PUBLIC_RELATIVE_PATH
    if not public_root.is_dir():
        return set()
    return {
        path.relative_to(root).as_posix()
        for path in public_root.rglob('*')
        if path.is_file()
    }


def declared_public_files(entries: Iterable[Mapping[str, Any]]) -> set[str]:
    prefix = PUBLIC_RELATIVE_PATH.as_posix() + '/'
    return {
        entry['filename']
        for entry in entries
        if isinstance(entry.get('filename'), str)
        and '#' not in entry['filename']
        and entry['filename'].startswith(prefix)
    }


def missing_public_entries(
    public_files: Iterable[str],
    entries: Iterable[Mapping[str, Any]],
) -> set[str]:
    return set(public_files) - declared_public_files(entries)


def _validate_schema_contract(schema: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(schema, dict):
        return ['asset provenance schema must be a JSON object']
    if schema.get('$schema') != 'https://json-schema.org/draft/2020-12/schema':
        errors.append('schema must declare JSON Schema draft 2020-12')
    schema_required = set(schema.get('required', []))
    if schema_required != REQUIRED_TOP_LEVEL_FIELDS:
        errors.append('schema top-level required fields do not match the guard contract')
    try:
        entry_required = set(schema['$defs']['entry']['required'])
    except (KeyError, TypeError):
        errors.append('schema must define $defs.entry.required')
    else:
        if entry_required != REQUIRED_ENTRY_FIELDS:
            errors.append('schema entry required fields do not match the guard contract')
    return errors


def _validate_entry(
    entry: object,
    *,
    index: int,
    root: Path,
    audit_date: date | None,
    notices: str,
) -> list[str]:
    if not isinstance(entry, dict):
        return [f'entries[{index}] must be an object']

    label = entry.get('filename') if isinstance(entry.get('filename'), str) else f'entries[{index}]'
    errors: list[str] = []
    missing = REQUIRED_ENTRY_FIELDS - entry.keys()
    if missing:
        errors.append(f'{label}: missing required fields: {", ".join(sorted(missing))}')
        return errors

    filename = entry['filename']
    if not _is_nonempty_string(filename):
        errors.append(f'{label}: filename must be a non-empty string')
    elif '\\' in filename or filename.startswith('/') or '..' in Path(_physical_filename(filename)).parts:
        errors.append(f'{label}: filename must be a safe repository-relative POSIX path')

    for field in ('license', 'creator', 'attribution_text', 'verification_method'):
        if not _is_nonempty_string(entry[field]):
            errors.append(f'{label}: {field} must be a non-empty string')

    if entry['asset_type'] not in ASSET_TYPES:
        errors.append(f'{label}: invalid asset_type {entry["asset_type"]!r}')
    if entry['distribution'] not in DISTRIBUTIONS:
        errors.append(f'{label}: invalid distribution {entry["distribution"]!r}')
    if entry['source_kind'] not in SOURCE_KINDS:
        errors.append(f'{label}: invalid source_kind {entry["source_kind"]!r}')
    if entry['rights_status'] not in RIGHTS_STATUSES:
        errors.append(f'{label}: invalid rights_status {entry["rights_status"]!r}')

    if not isinstance(entry['frontier_derived'], bool):
        errors.append(f'{label}: frontier_derived must be boolean')
    if not isinstance(entry['commercial_use_approved'], bool):
        errors.append(f'{label}: commercial_use_approved must be boolean')
    if entry['frontier_derived'] is True and entry['commercial_use_approved'] is not False:
        errors.append(f'{label}: Frontier-derived material is not approved for commercial use')
    if entry['rights_status'] in {'noncommercial_only', 'unresolved'} and entry['commercial_use_approved'] is not False:
        errors.append(f'{label}: restricted or unresolved rights cannot approve commercial use')

    source_url = entry['source_url']
    if entry['source_kind'] == 'original':
        if source_url is not None:
            errors.append(f'{label}: original assets must use null source_url')
    elif not _is_https_url(source_url):
        errors.append(f'{label}: non-original assets require an HTTPS source_url')

    approved_on = _parse_iso_date(entry['approval_date'])
    if approved_on is None:
        errors.append(f'{label}: approval_date must be an ISO calendar date')
    elif audit_date is not None and approved_on > audit_date:
        errors.append(f'{label}: approval_date cannot be after audit_date')

    notice_reference = entry['notice_reference']
    if notice_reference is not None:
        if not _is_nonempty_string(notice_reference):
            errors.append(f'{label}: notice_reference must be null or a non-empty string')
        elif notice_reference not in notices:
            errors.append(f'{label}: THIRD_PARTY_NOTICES.md is missing {notice_reference!r}')

    distribution = entry['distribution']
    expected_sha = entry['sha256']
    if distribution == 'runtime_external':
        if expected_sha is not None:
            errors.append(f'{label}: runtime_external entries must use null sha256')
    elif _is_nonempty_string(filename):
        physical_path = root / _physical_filename(filename)
        if not physical_path.is_file():
            errors.append(f'{label}: bundled file does not exist')
        elif not isinstance(expected_sha, str) or len(expected_sha) != 64:
            errors.append(f'{label}: bundled files require a lowercase SHA-256')
        else:
            actual_sha = _sha256(physical_path)
            if actual_sha != expected_sha:
                errors.append(
                    f'{label}: SHA-256 drift (manifest {expected_sha}, actual {actual_sha})'
                )

    return errors


def validate_manifest(root: Path = ROOT) -> list[str]:
    root = root.resolve()
    manifest_path = root / MANIFEST_RELATIVE_PATH
    schema_path = root / SCHEMA_RELATIVE_PATH
    notices_path = root / NOTICES_RELATIVE_PATH
    errors: list[str] = []

    for path, description in (
        (manifest_path, 'asset provenance manifest'),
        (schema_path, 'asset provenance schema'),
        (notices_path, 'third-party notices'),
    ):
        if not path.is_file():
            errors.append(f'missing {description}: {path.relative_to(root).as_posix()}')
    if errors:
        return errors

    try:
        manifest = _read_json(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        return [f'cannot parse {MANIFEST_RELATIVE_PATH.as_posix()}: {exc}']
    try:
        schema = _read_json(schema_path)
    except (OSError, json.JSONDecodeError) as exc:
        return [f'cannot parse {SCHEMA_RELATIVE_PATH.as_posix()}: {exc}']

    errors.extend(_validate_schema_contract(schema))
    if not isinstance(manifest, dict):
        return errors + ['asset provenance manifest must be a JSON object']

    missing_top_level = REQUIRED_TOP_LEVEL_FIELDS - manifest.keys()
    if missing_top_level:
        return errors + [
            'manifest missing top-level fields: ' + ', '.join(sorted(missing_top_level))
        ]
    if manifest['$schema'] != './PROVENANCE.schema.json':
        errors.append('manifest $schema must be ./PROVENANCE.schema.json')
    if manifest['schema_version'] != 1:
        errors.append('manifest schema_version must be 1')
    if manifest['policy'] != 'assets/README.md':
        errors.append('manifest policy must be assets/README.md')

    audit_date = _parse_iso_date(manifest['audit_date'])
    if audit_date is None:
        errors.append('manifest audit_date must be an ISO calendar date')

    entries = manifest['entries']
    if not isinstance(entries, list) or not entries:
        return errors + ['manifest entries must be a non-empty array']

    notices = notices_path.read_text(encoding='utf-8')
    for index, entry in enumerate(entries):
        errors.extend(
            _validate_entry(
                entry,
                index=index,
                root=root,
                audit_date=audit_date,
                notices=notices,
            )
        )

    filenames = [entry.get('filename') for entry in entries if isinstance(entry, dict)]
    string_filenames = [value for value in filenames if isinstance(value, str)]
    duplicates = sorted({value for value in string_filenames if string_filenames.count(value) > 1})
    if duplicates:
        errors.append('duplicate manifest filenames: ' + ', '.join(duplicates))
    if string_filenames != sorted(string_filenames):
        errors.append('manifest entries must be sorted by filename')

    public_files = collect_public_files(root)
    missing_public = sorted(missing_public_entries(public_files, entries))
    stale_public = sorted(declared_public_files(entries) - public_files)
    if missing_public:
        errors.append('public files missing provenance entries: ' + ', '.join(missing_public))
    if stale_public:
        errors.append('provenance entries reference missing public files: ' + ', '.join(stale_public))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--root',
        type=Path,
        default=ROOT,
        help='Repository root (defaults to the root containing this script).',
    )
    args = parser.parse_args()

    errors = validate_manifest(args.root)
    if errors:
        print('Asset provenance validation failed:')
        for error in errors:
            print(f'  - {error}')
        return 1

    manifest = _read_json(args.root / MANIFEST_RELATIVE_PATH)
    public_count = len(collect_public_files(args.root))
    print(
        f'Asset provenance valid: {len(manifest["entries"])} entries, '
        f'{public_count} public files covered.'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
