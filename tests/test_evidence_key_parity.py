from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
EDDN_SRC = ROOT / 'apps' / 'eddn' / 'src'

for path in (API_SRC, IMPORTER_SRC, EDDN_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')

from evidence_store import store as api_store  # noqa: E402
import canonical_evidence as eddn_canonical  # noqa: E402
import canonical_evidence_promotion as importer_promotion  # noqa: E402


def test_content_addressed_evidence_key_matches_across_api_importer_and_eddn():
    payload = {
        'system_id64': 4242424242,
        'source_name': 'canonical_app_data',
        'subject_type': 'system',
        'subject_id': '4242424242',
        'evidence_type': 'station_set',
        'observed_at': datetime(2026, 7, 11, 12, 34, 56, tzinfo=timezone.utc),
        'source_record_id': None,
        'value': {
            'station_count': 12,
            'linked_station_count': 11,
            'system_name': 'Shinrarta Dezhra',
        },
    }

    api_key = api_store._content_addressed_evidence_key(payload)
    importer_key = importer_promotion._content_addressed_evidence_key(payload)
    eddn_key = eddn_canonical._content_addressed_evidence_key(payload)

    assert api_key == importer_key == eddn_key


def test_content_addressed_evidence_key_normalises_iso8601_z_suffix_consistently():
    payload = {
        'system_id64': 4242424242,
        'source_name': 'canonical_app_data',
        'subject_type': 'system',
        'subject_id': '4242424242',
        'evidence_type': 'colonisation_status',
        'observed_at': '2026-07-11T12:34:56Z',
        'source_record_id': 'frontier:run:123',
        'value': {
            'is_colonised': True,
            'is_being_colonised': False,
        },
    }

    api_key = api_store._content_addressed_evidence_key(payload)
    importer_key = importer_promotion._content_addressed_evidence_key(payload)
    eddn_key = eddn_canonical._content_addressed_evidence_key(payload)

    assert api_key == importer_key == eddn_key
