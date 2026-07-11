from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', 'NUL')

ROOT = Path(__file__).resolve().parents[1]
EDDN_SRC = ROOT / 'apps' / 'eddn' / 'src'
if str(EDDN_SRC) not in sys.path:
    sys.path.insert(0, str(EDDN_SRC))

import eddn_listener  # noqa: E402


@pytest.mark.asyncio
async def test_handle_colonisation_status_marks_pending_system_as_being_colonised():
    eddn_listener._pending_systems.clear()

    await eddn_listener.handle_colonisation_status(
        None,
        {},
        {
            'event': 'ColonisationConstructionDepot',
            'SystemAddress': 12866676218109,
            'StarSystem': 'Test Colonisation System',
        },
    )

    pending = eddn_listener._pending_systems[12866676218109]
    assert pending['name'] == 'Test Colonisation System'
    assert pending['is_colonised'] is False
    assert pending['is_being_colonised'] is True


def test_colonisation_status_from_message_handles_explicit_completion_and_generic_prefix():
    assert eddn_listener._colonisation_status_from_message(
        {'event': 'Colonisation', 'ColonisationState': 'Colonised'}
    ) == (True, False)
    assert eddn_listener._colonisation_status_from_message(
        {'event': 'ColonisationContribution'}
    ) == (False, True)


def test_listener_uses_local_canonical_evidence_module():
    assert eddn_listener.promote_canonical_evidence_for_systems.__module__ == 'canonical_evidence'
