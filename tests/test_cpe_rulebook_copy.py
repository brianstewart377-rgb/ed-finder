"""The runtime rulebook is the exact pinned CRE release, with usable citations."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))

from edfinder_api.cpe import RULEBOOK_RELEASE, rule  # noqa: E402
from edfinder_api.cpe.explain import explain_rule  # noqa: E402


def test_runtime_rulebook_matches_the_pin_and_docs_bytes():
    directory = ROOT / 'docs' / 'reference' / 'colonisation' / 'cre-rulebook'
    pin = json.loads((directory / 'pin.json').read_text(encoding='utf-8'))
    runtime = (ROOT / 'apps' / 'api' / 'src' / 'cpe' / 'data' / 'rulebook.json').read_bytes()

    assert hashlib.sha256(runtime).hexdigest() == pin['sha256']
    assert runtime == (directory / 'rulebook.json').read_bytes()
    assert RULEBOOK_RELEASE == pin['release_tag'] == 'cre-knowledge-v0.4.0'


def test_rules_preserve_status_and_first_source_citations():
    data = json.loads(
        (ROOT / 'apps' / 'api' / 'src' / 'cpe' / 'data' / 'rulebook.json').read_text(
            encoding='utf-8',
        )
    )
    for item in data['rules']:
        actual = rule(item['id'])
        assert actual.topic == item['topic']
        assert actual.quote == item['sources'][0]['quote']
        assert actual.page == item['sources'][0].get('page')
        assert explain_rule(item['id']) == {
            key: getattr(actual, key)
            for key in ('id', 'title', 'status', 'statement', 'quote', 'page')
        }
    assert rule('RB-0003').status == 'Extracted'
    with pytest.raises(FrozenInstanceError):
        rule('RB-0003').status = 'Confirmed'


def test_unknown_rule_fails_closed():
    with pytest.raises(KeyError, match='RB-9999'):
        rule('RB-9999')
