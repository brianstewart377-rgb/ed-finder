import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from scripts.checks.asset_provenance import (
    collect_public_files,
    declared_public_files,
    missing_public_entries,
    validate_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / 'assets' / 'PROVENANCE.json'
SCHEMA_PATH = ROOT / 'assets' / 'PROVENANCE.schema.json'
NOTICES_PATH = ROOT / 'THIRD_PARTY_NOTICES.md'


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))


def test_provenance_manifest_conforms_to_json_schema():
    manifest = _manifest()
    schema = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    errors = sorted(validator.iter_errors(manifest), key=lambda error: list(error.path))

    assert not errors, '\n'.join(error.message for error in errors)


def test_provenance_guard_accepts_the_repository_inventory():
    assert validate_manifest(ROOT) == []


def test_every_public_file_has_one_exact_provenance_entry():
    entries = _manifest()['entries']
    public_files = collect_public_files(ROOT)

    assert declared_public_files(entries) == public_files
    assert len([entry for entry in entries if entry['filename'].startswith('frontend/public/')]) == len(public_files)


def test_missing_public_entry_detection_rejects_a_future_asset():
    entries = _manifest()['entries']
    future_asset = 'frontend/public/media/future-asset.ogg'
    simulated_public_files = collect_public_files(ROOT) | {future_asset}

    assert missing_public_entries(simulated_public_files, entries) == {future_asset}


def test_third_party_notice_references_are_present():
    notices = NOTICES_PATH.read_text(encoding='utf-8')
    required_references = {
        entry['notice_reference']
        for entry in _manifest()['entries']
        if entry['notice_reference'] is not None
    }

    assert required_references
    assert all(reference in notices for reference in required_references)
    assert 'ESO/Digitized Sky Survey 2. Acknowledgment: Davide De Martin' in notices
    assert 'No EDAssets media file is currently bundled' in notices
    assert 'SIL Open Font License, Version 1.1' in notices
