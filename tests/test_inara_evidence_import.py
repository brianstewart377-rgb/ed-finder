from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

from inara_evidence_import import (  # noqa: E402
    build_station_service_evidence_records,
    canonical_station_subject_id,
    normalise_requested_system_names,
    normalise_services,
)


class InaraEvidenceImportTests(unittest.TestCase):
    def test_normalise_requested_system_names_dedupes_blanks_and_case(self) -> None:
        names = normalise_requested_system_names([' Shinrarta Dezhra ', '', 'sol', 'SOL', 'Sol'])

        self.assertEqual(names, ['Shinrarta Dezhra', 'sol'])

    def test_normalise_services_dedupes_case_insensitively(self) -> None:
        services = normalise_services(['Market', 'market', ' Outfitting ', '', None, 'Shipyard'])

        self.assertEqual(services, ['Market', 'Outfitting', 'Shipyard'])

    def test_build_station_service_evidence_records_shapes_bounded_snapshot(self) -> None:
        fetched_at = datetime(2026, 7, 6, 21, 0, tzinfo=timezone.utc)
        records = build_station_service_evidence_records(
            system_id64=10477373803,
            requested_name='Shinrarta Dezhra',
            fetched_at=fetched_at,
            payload={
                'name': 'Shinrarta Dezhra',
                'inara_url': 'https://inara.cz/elite/starsystem/1',
                'allegiance': 'Pilots Federation',
                'government': 'Democracy',
                'economy': 'High Tech',
                'second_economy': 'Industrial',
                'security': 'High',
                'population': 100,
                'controlling_faction': 'Pilots Federation Local Branch',
                'stations': [
                    {
                        'name': 'Jameson Memorial',
                        'type': 'Orbis Starport',
                        'distance_ls': 508,
                        'services': ['Market', 'Outfitting', 'market'],
                        'economy': 'High Tech',
                        'inara_url': 'https://inara.cz/elite/station/1',
                    },
                ],
            },
            source_run_key='inara-station-services-20260706T210000Z',
            trigger_context='manual_operator_source',
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record['source_name'], 'inara')
        self.assertEqual(record['subject_type'], 'station')
        self.assertEqual(
            record['subject_id'],
            canonical_station_subject_id(10477373803, 'Jameson Memorial'),
        )
        self.assertEqual(record['evidence_type'], 'station_services_snapshot')
        self.assertEqual(record['value_json']['services'], ['Market', 'Outfitting'])
        self.assertEqual(record['value_json']['system_context']['economy'], 'High Tech')
        self.assertEqual(record['metadata_json']['writer'], 'inara_evidence_import')
        self.assertIn('station_services', record['tags_json'])
        self.assertTrue(record['evidence_key'].startswith('inara-station-services:'))
        self.assertEqual(record['observed_at'], '2026-07-06T21:00:00Z')


if __name__ == '__main__':
    unittest.main()
