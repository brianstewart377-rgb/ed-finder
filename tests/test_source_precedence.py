from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'

if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from source_precedence import merge_body_scan_fact  # noqa: E402


def test_body_scan_precedence_prefers_journal_over_single_eddn_source():
    existing = {
        'system_address': 10,
        'body_id': 7,
        'body_name': 'Alpha 7',
        'planet_class': 'High metal content world',
        'is_landable': False,
        'data_sources': ['eddn_scan'],
        'confidence': 0.7,
    }
    incoming = {
        'system_address': 10,
        'body_id': 7,
        'body_name': 'Alpha 7',
        'planet_class': 'Rocky body',
        'is_landable': True,
        'data_sources': ['frontier_journal_scan'],
        'confidence': 0.9,
    }

    decision = merge_body_scan_fact(existing, incoming)

    assert decision.resolution == 'prefer_incoming'
    assert decision.row['planet_class'] == 'Rocky body'
    assert decision.row['is_landable'] is True
    assert decision.row['data_sources'] == ['eddn_scan', 'frontier_journal_scan']
    assert decision.row['confidence'] == 0.9


def test_body_scan_precedence_preserves_existing_multi_source_consensus_against_journal():
    existing = {
        'system_address': 10,
        'body_id': 7,
        'body_name': 'Alpha 7',
        'planet_class': 'High metal content world',
        'is_landable': False,
        'data_sources': ['spansh_import', 'eddn_scan'],
        'confidence': 0.95,
    }
    incoming = {
        'system_address': 10,
        'body_id': 7,
        'body_name': 'Alpha 7',
        'planet_class': 'Rocky body',
        'is_landable': True,
        'data_sources': ['frontier_journal_scan'],
        'confidence': 0.9,
    }

    decision = merge_body_scan_fact(existing, incoming)

    assert decision.resolution == 'preserve_existing_consensus'
    assert decision.row['planet_class'] == 'High metal content world'
    assert decision.row['is_landable'] is False
    assert decision.row['data_sources'] == ['spansh_import', 'eddn_scan', 'frontier_journal_scan']
    assert decision.row['confidence'] == 0.95
