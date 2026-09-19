"""Static contract for the governed spatial-pyramid operator script.

No SSH, no DB, no prod: reads the script text and asserts it pins the canonical
generation, gates on migration 012, and exposes build + publish sub-commands.
"""
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'operator' / 'actions' / 'v3-spatial-pyramid.sh'


def test_script_exists():
    assert _SCRIPT.is_file()


def test_pins_canonical_generation_not_ratings_key():
    text = _SCRIPT.read_text(encoding='utf-8')
    assert 'TARGET_CANONICAL_GENERATION=' in text
    assert 'TARGET_CANONICAL_SEQUENCE=' in text
    # The decoupled build must NOT pin a ratings derived generation_key.
    assert 'ratings_v4_prod_p4_opt1' not in text
    assert 'TARGET_GENERATION_KEY' not in text


def test_gates_on_migration_012():
    text = _SCRIPT.read_text(encoding='utf-8')
    assert '012_v3_spatial_pyramid_decouple.sql' in text


def test_exposes_build_and_publish_commands():
    text = _SCRIPT.read_text(encoding='utf-8')
    assert 'publish_spatial_pyramid' in text
    assert ' build)' in text or 'build)' in text
    assert ' publish)' in text or 'publish)' in text
